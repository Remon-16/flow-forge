"""测试所有 prompt 模板的国际化是否正确。
Test that internationalization is correctly applied to all prompt templates.

自动发现所有含 {{language}} / {language} 占位符的模板，验证 render_prompt()
能正确替换，并检查 get_language_name() 和 _LANGUAGE_NAMES 的行为。
"""

import ast
import importlib.util
import os
import sys
from pathlib import Path
from typing import Dict, Optional

import pytest

# 确保 agent/ 在 sys.path 中 / Ensure agent/ is on sys.path
_AGENT_DIR = Path(__file__).resolve().parent.parent
if str(_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENT_DIR))

# 直接加载 prompts/render.py，绕过 prompts/__init__.py（后者会触发 flow_forge_schemas 导入）
# Load prompts/render.py directly, bypassing prompts/__init__.py
# (which triggers flow_forge_schemas import chain)
_render_path = _AGENT_DIR / "prompts" / "render.py"
_render_spec = importlib.util.spec_from_file_location(
    "prompts.render", str(_render_path)
)
_render_mod = importlib.util.module_from_spec(_render_spec)
_render_spec.loader.exec_module(_render_mod)
render_prompt = _render_mod.render_prompt


# ============================================================================
# 辅助：AST 解析 — 从 .py 文件中提取模板字符串，无需 import 模块
# Helpers: AST parsing — extract template strings from .py files without importing
# ============================================================================


def _extract_string_value(node: ast.AST) -> str:
    """从 AST 节点提取字符串值 — 支持普通字符串和 f-string。
    Extract string value from AST node — supports plain strings and f-strings.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        # f-string: 拼接所有 Constant 节点 / concatenate all Constant parts
        parts = []
        for part in node.values:
            if isinstance(part, ast.Constant) and isinstance(part.value, str):
                parts.append(part.value)
            elif isinstance(part, ast.FormattedValue):
                # 真正的 f-string 插值 — 无法静态求值 / real interpolation — can't evaluate
                parts.append("{...}")
        return "".join(parts)
    return ""


def _has_language_placeholder(template: str) -> bool:
    """检查模板是否包含 {{language}} 或 {language} 占位符。
    Check if template contains {{language}} or {language} placeholder.
    """
    return "{{language}}" in template or "{language}" in template


def _discover_templates_from_dir(prompts_dir: Path) -> Dict[str, str]:
    """从目录中所有 .py 文件提取含 {language} 占位符的模板变量。
    Extract template variables containing {language} placeholder from all .py files.

    Returns:
        { "module_name.VAR_NAME": template_string, ... }
    """
    found: Dict[str, str] = {}

    for py_file in sorted(prompts_dir.glob("*.py")):
        if py_file.name.startswith("_") and py_file.name != "__init__.py":
            continue
        mod_name = py_file.stem
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source)
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id.isupper():
                            value = _extract_string_value(node.value)
                            if value and _has_language_placeholder(value):
                                key = f"{mod_name}.{target.id}"
                                found[key] = value
        except SyntaxError:
            continue

    return found


# ============================================================================
# 自动发现 / Auto-discovery
# ============================================================================


_PROMPTS_DIR = _AGENT_DIR / "prompts"
_PLUGIN_PROMPTS_DIR = _AGENT_DIR / "plugins" / "official" / "prompts"


def _discover_all_templates() -> Dict[str, str]:
    """发现所有含 {{language}} 占位符的 prompt 模板。
    Discover all prompt templates containing {{language}} placeholder.
    """
    templates: Dict[str, str] = {}

    for directory in (_PROMPTS_DIR, _PLUGIN_PROMPTS_DIR):
        if directory.is_dir():
            templates.update(_discover_templates_from_dir(directory))

    return templates


# 模块级别缓存 / Module-level cache
_ALL_TEMPLATES: Optional[Dict[str, str]] = None


def all_templates() -> Dict[str, str]:
    """返回所有已发现的模板（缓存结果）。Return all discovered templates (cached)."""
    global _ALL_TEMPLATES
    if _ALL_TEMPLATES is None:
        _ALL_TEMPLATES = _discover_all_templates()
    return _ALL_TEMPLATES


# ============================================================================
# 测试数据 / Test data
# ============================================================================

# 模拟纯字符串模板（运行时 {{language}} 保持为双层花括号）
# Mimic plain string template ({{language}} stays as double braces at runtime)
_PLAIN_TEMPLATE = "You MUST write all content in {{language}}. Do NOT use any other language."

# 模拟 f-string 模板（运行时 {language} 变成单层花括号）
# Mimic f-string template ({language} becomes single braces at runtime after f-string eval)
_FSTRING_TEMPLATE = "You MUST write all content in {language}. Do NOT use any other language."


# ============================================================================
# 测试类 / Test classes
# ============================================================================


class TestRenderPromptI18n:
    """测试 render_prompt() 的 {{language}} 替换行为。
    Test {{language}} substitution behavior of render_prompt().
    """

    ZH_NAME = "简体中文"
    EN_NAME = "English"

    def should_replace_double_braces_in_plain_templates(self):
        """纯字符串模板中 {{language}} 应被完整替换。
        {{language}} in plain string templates should be fully replaced.
        """
        result = render_prompt(_PLAIN_TEMPLATE, language=self.ZH_NAME)
        assert "{{language}}" not in result
        assert "{language}" not in result
        assert self.ZH_NAME in result
        # 不应残留任何花括号 / No stray braces should remain
        assert "{简体中文}" not in result

    def should_replace_single_braces_in_fstring_templates(self):
        """f-string 模板中 {language} 应被完整替换。
        {language} in f-string templates should be fully replaced.
        """
        result = render_prompt(_FSTRING_TEMPLATE, language=self.ZH_NAME)
        assert "{{language}}" not in result
        assert "{language}" not in result
        assert self.ZH_NAME in result

    def should_produce_same_result_for_both_template_types(self):
        """两种模板类型替换后结果应一致。
        Both template types should produce identical results after substitution.
        """
        plain_result = render_prompt(_PLAIN_TEMPLATE, language=self.ZH_NAME)
        fstring_result = render_prompt(_FSTRING_TEMPLATE, language=self.ZH_NAME)
        assert plain_result == fstring_result

    def should_replace_with_english(self):
        """使用 en_US 时 {language} 应替换为 English。
        {language} should be replaced with English for en_US.
        """
        for template in (_PLAIN_TEMPLATE, _FSTRING_TEMPLATE):
            result = render_prompt(template, language=self.EN_NAME)
            assert self.EN_NAME in result
            assert "{{language}}" not in result
            assert "{language}" not in result

    def should_not_trigger_unresolved_warning_for_language(self):
        """替换后不应残留未解析的 {{language}} 占位符。
        No unresolved {{language}} placeholder should remain after substitution.
        """
        for template in (_PLAIN_TEMPLATE, _FSTRING_TEMPLATE):
            result = render_prompt(template, language=self.ZH_NAME)
            remaining = _render_mod._VAR_RE.findall(result)
            assert "language" not in remaining, (
                f"{{{{language}}}} still found in: {result[:80]}..."
            )


class TestDiscoveredTemplates:
    """对所有已发现模板的国际化测试。
    I18n tests for all discovered templates.
    """

    ZH_NAME = "简体中文"
    EN_NAME = "English"

    @pytest.mark.parametrize("template_key,template_str", [
        (k, v) for k, v in sorted(_discover_all_templates().items())
    ])
    def should_replace_language_in_template(self, template_key, template_str):
        """每个已发现模板的 {{language}} 应被正确替换。
        {{language}} in each discovered template should be correctly replaced.
        """
        result = render_prompt(template_str, language=self.ZH_NAME)
        assert "{{language}}" not in result, (
            f"{template_key}: double-brace placeholder not replaced"
        )
        assert "{language}" not in result, (
            f"{template_key}: single-brace placeholder not replaced"
        )
        assert self.ZH_NAME in result, (
            f"{template_key}: language name not found in rendered output"
        )

    @pytest.mark.parametrize("template_key,template_str", [
        (k, v) for k, v in sorted(_discover_all_templates().items())
    ])
    def should_replace_with_english_for_all(self, template_key, template_str):
        """每个已发现模板使用 en_US 时应替换为 English。
        Each discovered template should use English when AGENT_LANG=en_US.
        """
        result = render_prompt(template_str, language=self.EN_NAME)
        assert "{{language}}" not in result, (
            f"{template_key}: double-brace placeholder not replaced"
        )
        assert "{language}" not in result, (
            f"{template_key}: single-brace placeholder not replaced"
        )
        assert self.EN_NAME in result, (
            f"{template_key}: 'English' not found in rendered output"
        )

    def should_find_all_expected_templates(self):
        """应能发现所有已知的国际标准化模板。
        Should discover all known internationalized templates.
        """
        names = set(all_templates().keys())
        # 所有已知含 {{language}} 的模板 / All known templates with {{language}}
        expected = {
            # prompts/plan_generation.py
            "plan_generation.PLAN_GENERATION_SYSTEM",
            "plan_generation.PLAN_CHUNK_GLOBAL_SYSTEM",
            "plan_generation.PLAN_CHUNK_API_SECTION_SYSTEM",
            "plan_generation.PLAN_CHUNK_BIZ_SECTION_SYSTEM",
            # prompts/plan_outline.py
            "plan_outline.PLAN_OUTLINE_SYSTEM",
            # prompts/plan_reviser.py
            "plan_reviser.PLAN_REVISER_SYSTEM",
            "plan_reviser.PLAN_ANNOTATION_INTENT_SYSTEM",
            "plan_reviser.PLAN_ANNOTATION_UPDATE_SYSTEM",
            "plan_reviser.PLAN_ANNOTATION_ADD_SYSTEM",
            # prompts/skeleton_generation.py (f-string)
            "skeleton_generation.SINGLE_SKELETON_SYSTEM",
            "skeleton_generation.BIZ_SKELETON_SYSTEM",
            # prompts/doc_parser.py (f-string)
            "doc_parser.DOC_PARSER_SYSTEM",
            # prompts/api_analyzer.py (f-string)
            "api_analyzer.API_ANALYSIS_SYSTEM",
            # prompts/case_generation.py (f-string)
            "case_generation.CASE_GENERATION_SYSTEM",
        }
        missing = expected - names
        assert not missing, f"Missing templates: {missing}"


class TestLanguageNameMapping:
    """测试 get_language_name() 和 _LANGUAGE_NAMES 映射。
    Test get_language_name() and _LANGUAGE_NAMES mapping.
    """

    def should_have_non_empty_values(self):
        """_LANGUAGE_NAMES 每个 value 应为非空字符串。
        Each _LANGUAGE_NAMES value should be a non-empty string.
        """
        from i18n.loader import _LANGUAGE_NAMES

        assert len(_LANGUAGE_NAMES) >= 2
        for key, value in _LANGUAGE_NAMES.items():
            assert isinstance(key, str) and key, f"Key '{key}' is empty"
            assert isinstance(value, str) and value, f"Value for '{key}' is empty"

    def should_return_chinese_by_default(self):
        """未设置 AGENT_LANG 时应返回中文名称。
        Should return Chinese name when AGENT_LANG is not set.
        """
        from i18n.loader import get_language_name

        # 保存并移除环境变量 / Save and remove env var
        saved = os.environ.pop("AGENT_LANG", None)
        try:
            name = get_language_name()
            assert "简体中文" in name
        finally:
            if saved is not None:
                os.environ["AGENT_LANG"] = saved

    def should_return_english_for_en_us(self):
        """AGENT_LANG=en_US 时应返回 English。
        Should return 'English' when AGENT_LANG=en_US.
        """
        from i18n.loader import get_language_name

        saved = os.environ.get("AGENT_LANG")
        os.environ["AGENT_LANG"] = "en_US"
        try:
            name = get_language_name()
            assert name == "English"
        finally:
            if saved is not None:
                os.environ["AGENT_LANG"] = saved
            else:
                os.environ.pop("AGENT_LANG", None)

    def should_fallback_to_chinese_for_unknown_locale(self):
        """未知语言代码应回退到中文。
        Unknown locale should fall back to Chinese.
        """
        from i18n.loader import get_language_name

        saved = os.environ.get("AGENT_LANG")
        os.environ["AGENT_LANG"] = "ja_JP"
        try:
            name = get_language_name()
            assert "简体中文" in name
        finally:
            if saved is not None:
                os.environ["AGENT_LANG"] = saved
            else:
                os.environ.pop("AGENT_LANG", None)

    def should_return_chinese_for_zh_cn_explicitly(self):
        """AGENT_LANG=zh_CN 时应显式返回中文名称。
        Should explicitly return Chinese name for AGENT_LANG=zh_CN.
        """
        from i18n.loader import get_language_name

        saved = os.environ.get("AGENT_LANG")
        os.environ["AGENT_LANG"] = "zh_CN"
        try:
            name = get_language_name()
            assert "简体中文" in name
            assert "Simplified Chinese" not in name
        finally:
            if saved is not None:
                os.environ["AGENT_LANG"] = saved
            else:
                os.environ.pop("AGENT_LANG", None)

    def should_export_language_names_dict(self):
        """_LANGUAGE_NAMES 应可从 loader 模块直接导入。
        _LANGUAGE_NAMES should be importable from loader module.
        """
        from i18n.loader import _LANGUAGE_NAMES

        assert "zh_CN" in _LANGUAGE_NAMES
        assert "en_US" in _LANGUAGE_NAMES
        assert _LANGUAGE_NAMES["zh_CN"] == "简体中文"
        assert _LANGUAGE_NAMES["en_US"] == "English"


class TestRendererEdgeCases:
    """render_prompt() 边界情况测试。
    Edge case tests for render_prompt().
    """

    def should_handle_template_without_language_placeholder(self):
        """不含 {{language}} 的模板应原样返回（除其他变量外）。
        Template without {{language}} should be returned unchanged (except other vars).
        """
        template = "Hello {{name}}, welcome!"
        result = render_prompt(template, name="World")
        assert result == "Hello World, welcome!"

    def should_handle_multiple_placeholders(self):
        """应正确处理多个不同的占位符。
        Should correctly handle multiple different placeholders.
        """
        template = "Write in {{language}}. Use {{style}} tone."
        result = render_prompt(
            template,
            language="简体中文 (Simplified Chinese)",
            style="professional",
        )
        assert "简体中文" in result
        assert "professional" in result
        assert "{{language}}" not in result
        assert "{{style}}" not in result

    def should_handle_language_placeholder_appearing_multiple_times(self):
        """{{language}} 出现多次时每个都应被替换。
        Each occurrence of {{language}} should be replaced.
        """
        template = "{{language}} is required. Write in {{language}}."
        result = render_prompt(template, language="English")
        assert result.count("English") == 2
        assert "{{language}}" not in result
        assert "{language}" not in result

    def should_warn_on_unresolved_placeholders(self):
        """未提供对应值的占位符应触发警告。
        Unresolved placeholders should trigger a warning.
        """
        import logging
        import io

        # 捕获日志输出 / Capture log output
        logger = logging.getLogger("prompts.render")
        logger.setLevel(logging.WARNING)
        buf = io.StringIO()
        handler = logging.StreamHandler(buf)
        handler.setLevel(logging.WARNING)
        logger.addHandler(handler)

        try:
            render_prompt("Hello {{unresolved_var}}", language="English")
            log_output = buf.getvalue()
            assert "unresolved_var" in log_output
        finally:
            logger.removeHandler(handler)
