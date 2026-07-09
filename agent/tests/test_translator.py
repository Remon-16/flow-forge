"""Tests for the case translator agent, prompts, and detection heuristic.

All LLM calls are mocked — NO real API calls.
"""

import json
import logging
import io
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# 注入 shared/py 到 sys.path，使 flow_forge_schemas 和 agent 模块可导入
# Inject shared/py onto sys.path so flow_forge_schemas and agent modules are importable
_AGENT_DIR = Path(__file__).resolve().parent.parent
_SHARED = os.path.normpath(os.path.join(str(_AGENT_DIR), "..", "shared", "py"))
if os.path.isdir(_SHARED) and _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)
if str(_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENT_DIR))

from agents.base import BaseAgent
from config.translate_settings import TranslateSettings
from prompts.render import render_prompt
from prompts.translator import TRANSLATOR_SYSTEM, TRANSLATOR_USER


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings(**kwargs) -> TranslateSettings:
    """Create a minimal TranslateSettings for testing."""
    defaults = dict(llm_api_key="test", target_lang="zh_CN", batch_size=10)
    defaults.update(kwargs)
    return TranslateSettings(**defaults)


def _prevent_real_client():
    """Prevent BaseAgent from creating a real OpenAI client."""
    BaseAgent._shared_client = MagicMock()


def _make_translator(settings=None):
    """Create a CaseTranslator with safe defaults."""
    _prevent_real_client()
    if settings is None:
        settings = _make_settings()
    from agents.translator import CaseTranslator
    return CaseTranslator(settings)


def _mock_call_llm(agent, return_value: str):
    """Replace agent.call_llm with a MagicMock returning given value."""
    mock = MagicMock()
    mock.return_value = return_value
    agent.call_llm = mock
    return mock


_SAMPLE_SINGLE_CASES = [
    {
        "case_type": "single",
        "test_id": "TC_API_CART_DELETE_001",
        "relevance_id": "api_api_cart_delete",
        "tag": "P1",
        "api_name": "DELETE /api/cart",
        "app_name": "default",
        "method": "DELETE",
        "url": "/api/cart",
        "request_head": {"Content-Type": "application/json"},
        "request_body": None,
        "status_code": 200,
        "assert_dict": {"code": "100000"},
        "assert_rules": None,
        "preprocessors": None,
        "postprocessors": None,
        "remark": "Negative case - Verify failure when providing invalid JWT token",
    },
    {
        "case_type": "single",
        "test_id": "TC_REGISTER_POS_001",
        "relevance_id": "api_api_auth_register_post",
        "tag": "P0",
        "api_name": "创建新用户账号 / Create new user account",
        "app_name": "default",
        "method": "POST",
        "url": "/api/auth/register",
        "request_head": {"Content-Type": "application/json"},
        "request_body": {"username": "test@example.com", "password": "Test@123"},
        "status_code": 200,
        "assert_dict": {"code": "100000"},
        "assert_rules": None,
        "preprocessors": None,
        "postprocessors": None,
        "remark": "Positive case - Normal registration",
    },
]

_TRANSLATED_SINGLE_CASES = [
    {
        "case_type": "single",
        "test_id": "TC_API_CART_DELETE_001",
        "relevance_id": "api_api_cart_delete",
        "tag": "P1",
        "api_name": "删除购物车",
        "app_name": "default",
        "method": "DELETE",
        "url": "/api/cart",
        "request_head": {"Content-Type": "application/json"},
        "request_body": None,
        "status_code": 200,
        "assert_dict": {"code": "100000"},
        "assert_rules": None,
        "preprocessors": None,
        "postprocessors": None,
        "remark": "反向用例 - 验证提供无效JWT令牌时的失败场景",
    },
    {
        "case_type": "single",
        "test_id": "TC_REGISTER_POS_001",
        "relevance_id": "api_api_auth_register_post",
        "tag": "P0",
        "api_name": "创建新用户账号",
        "app_name": "default",
        "method": "POST",
        "url": "/api/auth/register",
        "request_head": {"Content-Type": "application/json"},
        "request_body": {"username": "test@example.com", "password": "Test@123"},
        "status_code": 200,
        "assert_dict": {"code": "100000"},
        "assert_rules": None,
        "preprocessors": None,
        "postprocessors": None,
        "remark": "正向用例 - 正常注册流程",
    },
]


# ============================================================================
# TestTranslatorPromptRendering — prompt 模板替换测试
# ============================================================================


class TestTranslatorPromptRendering:
    """测试 translator prompt 中 {target_language} 和 {cases_json} 的替换。"""

    def should_replace_target_language_in_system_prompt(self):
        """TRANSLATOR_SYSTEM 中 {target_language} 应被替换为 "简体中文"。"""
        result = render_prompt(TRANSLATOR_SYSTEM, target_language="简体中文")
        assert "{target_language}" not in result
        assert "{{target_language}}" not in result
        assert "简体中文" in result
        # 不应残留旧的英文括号名称
        assert "Simplified Chinese" not in result

    def should_replace_target_language_with_english(self):
        """使用 English 时 {target_language} 应被替换为 "English"。"""
        result = render_prompt(TRANSLATOR_SYSTEM, target_language="English")
        assert "{target_language}" not in result
        assert "English" in result

    def should_replace_all_placeholders_in_user_prompt(self):
        """TRANSLATOR_USER 中三个占位符应全部正确替换。"""
        result = render_prompt(
            TRANSLATOR_USER,
            target_language="简体中文",
            cases_json='[{"test_id": "TC_001"}]',
        )
        assert "{target_language}" not in result
        assert "{cases_json}" not in result
        assert "简体中文" in result
        assert 'TC_001' in result

    def should_replace_all_placeholders_with_english(self):
        """使用 English 时所有占位符正确替换。"""
        result = render_prompt(
            TRANSLATOR_USER,
            target_language="English",
            cases_json="[]",
        )
        assert "{target_language}" not in result
        assert "{cases_json}" not in result
        assert "English" in result

    def should_warn_on_missing_cases_json(self):
        """未传递 cases_json 时应触发 unresolved placeholder 警告。"""
        logger_names = ["prompts.render", "prompts.render_prompt"]
        buf = io.StringIO()
        handler = logging.StreamHandler(buf)
        handler.setLevel(logging.WARNING)

        for name in logger_names:
            lg = logging.getLogger(name)
            lg.setLevel(logging.WARNING)
            lg.addHandler(handler)

        try:
            result = render_prompt(TRANSLATOR_USER, target_language="简体中文")
            log_output = buf.getvalue()
            # 结果中应有未替换的 {cases_json} / Result should contain unresolved placeholder
            assert "{cases_json}" in result or "cases_json" in log_output, (
                f"Expected unresolved cases_json placeholder. "
                f"Result: {result[:200]}..., Log: {log_output[:200]}"
            )
        finally:
            for name in logger_names:
                logging.getLogger(name).removeHandler(handler)


# ============================================================================
# TestNeedsTranslation — 启发式检测测试
# ============================================================================


class TestNeedsTranslation:
    """测试 needs_translation() 启发式检测函数。"""

    def should_return_false_for_pure_chinese_with_zh_target(self):
        """纯中文文本 + zh_CN 目标 → 不需要翻译。"""
        from agents.translator import CaseTranslator
        assert CaseTranslator.needs_translation("用户登录接口", "zh_CN") is False
        assert CaseTranslator.needs_translation("删除购物车商品", "zh_CN") is False

    def should_return_true_for_pure_english_with_zh_target(self):
        """纯英文文本 + zh_CN 目标 → 需要翻译。"""
        from agents.translator import CaseTranslator
        assert CaseTranslator.needs_translation("DELETE /api/cart", "zh_CN") is True
        assert CaseTranslator.needs_translation(
            "Negative case - Verify failure", "zh_CN"
        ) is True

    def should_return_true_for_mixed_text_with_zh_target(self):
        """双语混合文本 + zh_CN 目标 → 需要翻译。"""
        from agents.translator import CaseTranslator
        assert CaseTranslator.needs_translation(
            "创建用户 / Create user", "zh_CN"
        ) is True

    def should_return_false_for_empty_text(self):
        """空文本 → 不需要翻译。"""
        from agents.translator import CaseTranslator
        assert CaseTranslator.needs_translation("", "zh_CN") is False
        assert CaseTranslator.needs_translation("   ", "zh_CN") is False

    def should_return_false_for_pure_english_with_en_target(self):
        """纯英文 + en_US 目标 → 不需要翻译。"""
        from agents.translator import CaseTranslator
        assert CaseTranslator.needs_translation("User Login", "en_US") is False

    def should_return_true_for_pure_chinese_with_en_target(self):
        """纯中文 + en_US 目标 → 需要翻译。"""
        from agents.translator import CaseTranslator
        assert CaseTranslator.needs_translation("用户登录", "en_US") is True

    def should_handle_special_chars_only(self):
        """纯特殊字符/数字文本 → 不需要翻译。"""
        from agents.translator import CaseTranslator
        # 只有 / 和数字，不含字母 / Only slashes and digits, no letters
        assert CaseTranslator.needs_translation("/// 123 ///", "zh_CN") is False
        assert CaseTranslator.needs_translation("... --- ???", "zh_CN") is False

    def should_respect_custom_threshold(self):
        """自定义 threshold 应生效。"""
        from agents.translator import CaseTranslator
        # "用户Login" = 2 CJK (用户) + 5 ASCII (Login) = 7 alpha, CJK ratio ≈ 28.6%
        text = "用户Login"
        # threshold=0.5: 0.286 < 0.5 → True (needs translation)
        assert CaseTranslator.needs_translation(text, "zh_CN", threshold=0.5) is True
        # threshold=0.2: 0.286 >= 0.2 → False (already translated enough)
        assert CaseTranslator.needs_translation(text, "zh_CN", threshold=0.2) is False
        # Pure English with low threshold → still needs translation
        assert CaseTranslator.needs_translation("Hello World", "zh_CN", threshold=0.2) is True
        # Pure Chinese text should NOT need translation even with high threshold
        assert CaseTranslator.needs_translation("用户登录", "zh_CN", threshold=0.9) is False

    def test_case_needs_translation_detects_fields(self):
        """case_needs_translation() 应检测出需要翻译的字段列表。"""
        from agents.translator import CaseTranslator
        case = _SAMPLE_SINGLE_CASES[0].copy()  # DELETE /api/cart, English remark
        fields = CaseTranslator.case_needs_translation(case, "zh_CN", 0.5)
        assert "api_name" in fields
        assert "remark" in fields


# ============================================================================
# TestCaseTranslator — 翻译智能体测试 (mock LLM)
# ============================================================================


class TestCaseTranslator:
    """测试 CaseTranslator 类（mock call_llm）。"""

    def should_preserve_protected_fields_after_translation(self):
        """翻译后 test_id, method, url 等保护字段应保持不变。"""
        translator = _make_translator()
        _mock_call_llm(translator, json.dumps(_TRANSLATED_SINGLE_CASES))

        result = translator.translate_batch(_SAMPLE_SINGLE_CASES)
        assert len(result) == 2

        # 保护字段不变 / Protected fields unchanged
        for i in range(2):
            assert result[i]["test_id"] == _SAMPLE_SINGLE_CASES[i]["test_id"]
            assert result[i]["method"] == _SAMPLE_SINGLE_CASES[i]["method"]
            assert result[i]["url"] == _SAMPLE_SINGLE_CASES[i]["url"]
            assert result[i]["status_code"] == _SAMPLE_SINGLE_CASES[i]["status_code"]
            assert result[i]["tag"] == _SAMPLE_SINGLE_CASES[i]["tag"]

    def should_translate_text_fields(self):
        """翻译后 api_name, remark 应被修改。"""
        translator = _make_translator()
        _mock_call_llm(translator, json.dumps(_TRANSLATED_SINGLE_CASES))

        result = translator.translate_batch(_SAMPLE_SINGLE_CASES)
        # api_name 和 remark 应被翻译
        assert result[0]["api_name"] == "删除购物车"
        assert result[0]["remark"] != _SAMPLE_SINGLE_CASES[0]["remark"]

    def should_return_same_length_array(self):
        """返回的数组长度应与输入一致。"""
        translator = _make_translator()
        _mock_call_llm(translator, json.dumps(_TRANSLATED_SINGLE_CASES))

        result = translator.translate_batch(_SAMPLE_SINGLE_CASES)
        assert len(result) == len(_SAMPLE_SINGLE_CASES)

    def should_handle_json_wrapped_in_markdown_fences(self):
        """应能处理 markdown fence 包裹的 JSON 响应。"""
        translator = _make_translator()
        response = "```json\n" + json.dumps(_TRANSLATED_SINGLE_CASES) + "\n```"
        _mock_call_llm(translator, response)

        result = translator.translate_batch(_SAMPLE_SINGLE_CASES)
        assert len(result) == 2

    def should_fallback_to_original_on_parse_failure(self):
        """LLM 返回无法解析的内容时，应回退到原始数据。"""
        translator = _make_translator()
        _mock_call_llm(translator, "This is not valid JSON at all")

        result = translator.translate_batch(_SAMPLE_SINGLE_CASES)
        # 应返回原始数据 / Should return original data
        assert len(result) == 2
        assert result[0]["api_name"] == _SAMPLE_SINGLE_CASES[0]["api_name"]

    def should_fallback_on_length_mismatch(self):
        """LLM 返回的数组长度不匹配时，应回退。"""
        translator = _make_translator()
        # 只返回 1 个而非 2 个 / Return only 1 instead of 2
        _mock_call_llm(translator, json.dumps(_TRANSLATED_SINGLE_CASES[:1]))

        result = translator.translate_batch(_SAMPLE_SINGLE_CASES)
        assert len(result) == 2
        # 应回退原始数据 / Should fallback to original
        assert result[0]["api_name"] == _SAMPLE_SINGLE_CASES[0]["api_name"]

    def should_protect_fields_even_if_llm_modifies_them(self):
        """即使 LLM 意外修改了 test_id，字段保护也应覆盖回来。"""
        translator = _make_translator()

        # LLM 返回的数据中 test_id 被篡改 / LLM modified test_id
        modified = json.loads(json.dumps(_TRANSLATED_SINGLE_CASES))
        modified[0]["test_id"] = "TC_HACKED_001"
        _mock_call_llm(translator, json.dumps(modified))

        result = translator.translate_batch(_SAMPLE_SINGLE_CASES)
        # test_id 应被恢复为原始值 / test_id restored to original
        assert result[0]["test_id"] == _SAMPLE_SINGLE_CASES[0]["test_id"]

    def should_handle_dict_response_by_unwrapping(self):
        """LLM 返回 {"cases": [...]} 格式时，应解包为数组。"""
        translator = _make_translator()
        response = json.dumps({"cases": _TRANSLATED_SINGLE_CASES})
        _mock_call_llm(translator, response)

        result = translator.translate_batch(_SAMPLE_SINGLE_CASES)
        assert len(result) == 2

    def should_handle_many_batches_without_step_limit(self):
        """max_steps 不应限制批次数 — 翻译工具可处理超过 10 批。"""
        translator = _make_translator()
        _mock_call_llm(translator, json.dumps(_TRANSLATED_SINGLE_CASES))

        # 模拟 20 批翻译（每批 1 个用例），不应触发 ConvergenceError
        for _ in range(20):
            result = translator.translate_batch(_SAMPLE_SINGLE_CASES[:1])
            assert len(result) == 1

    def should_have_max_steps_set_to_unlimited(self):
        """CaseTranslator 的 _max_steps 应为 sys.maxsize（不受默认 10 限制）。"""
        translator = _make_translator()
        import sys
        assert translator._max_steps == sys.maxsize


# ============================================================================
# TestTranslateSettings — 配置加载测试
# ============================================================================


class TestTranslateSettings:
    """测试 TranslateSettings 和配置加载。"""

    def should_load_defaults(self):
        """应正确加载默认配置。"""
        settings = _make_settings()
        assert settings.llm_api_key == "test"
        assert settings.target_lang == "zh_CN"
        assert settings.batch_size == 10
        assert settings.detection_enabled is True
        assert settings.cjk_threshold == 0.5
        assert settings.log_to_output is False

    def should_override_from_kwargs(self):
        """关键字参数应覆盖默认值。"""
        settings = _make_settings(
            target_lang="en_US", batch_size=20,
            detection_enabled=False, cjk_threshold=0.7,
        )
        assert settings.target_lang == "en_US"
        assert settings.batch_size == 20
        assert settings.detection_enabled is False
        assert settings.cjk_threshold == 0.7
