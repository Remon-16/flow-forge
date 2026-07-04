"""用例字段翻译智能体 — 将已生成用例的文本字段翻译为目标语言。

Case field translation agent — translates text fields of generated test cases
into the target language. Uses JSON as intermediate format for LLM processing.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from .base import BaseAgent
from config.translate_settings import TranslateSettings
from prompts.render import render_prompt
from prompts.translator import TRANSLATOR_SYSTEM, TRANSLATOR_USER

logger = logging.getLogger(__name__)

# 非翻译字段 — 翻译后必须从原始数据恢复 / Non-translatable fields — must be
# restored from original data after translation to prevent LLM modification
_PROTECTED_FIELDS = frozenset({
    "test_id", "relevance_id", "step_id", "inherit",
    "method", "url", "status_code", "tag",
    "request_head", "request_body", "assert_dict", "assert_rules",
    "preprocessors", "postprocessors", "app_name", "case_type",
})

# 需要翻译的字段 / Translatable fields
_TRANSLATABLE_FIELDS = frozenset({"api_name", "sheet_name", "remark"})


class CaseTranslator(BaseAgent):
    """用例字段翻译智能体。

    Translates api_name, sheet_name, and remark fields of generated
    test cases to the target language. Uses JSON as intermediate format
    for more reliable LLM processing.
    """

    def __init__(self, settings: TranslateSettings):
        super().__init__(
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_output_tokens,
            base_url=settings.llm_base_url,
            context_window=settings.llm_context_window,
            max_output_tokens=settings.llm_max_output_tokens,
            rate_limit_delay=settings.llm_rate_limit_delay,
            retry_base_delay=settings.llm_retry_base_delay,
            max_concurrency=settings.llm_max_concurrency,
            request_timeout=settings.llm_request_timeout,
            extra_params=settings.llm_extra_params,
        )
        self.target_lang = settings.target_lang

    # ------------------------------------------------------------------
    # 目标语言可读名称 / Target language display name
    # ------------------------------------------------------------------

    def _language_display(self) -> str:
        """返回目标语言的 LLM 可读名称。

        Return a human-readable language name for prompt injection.
        """
        return "简体中文" if self.target_lang == "zh_CN" else "English"

    # ------------------------------------------------------------------
    # 已翻译检测 / Already-translated detection
    # ------------------------------------------------------------------

    @staticmethod
    def needs_translation(
        text: str,
        target_lang: str,
        threshold: float = 0.5,
    ) -> bool:
        """检测文本是否需要翻译到目标语言。

        Detect whether text needs translation to the target language.
        Uses a character-set heuristic:
          - zh_CN target: if CJK ratio >= threshold, consider already translated
          - en_US target: if ASCII alpha ratio >= threshold, consider already translated

        Args:
            text: 要检测的文本 / Text to check.
            target_lang: 目标语言 / Target language ("zh_CN" or "en_US").
            threshold: 字符占比阈值 / Character ratio threshold.

        Returns:
            True 表示需要翻译 / True if translation is needed.
        """
        if not text or not text.strip():
            return False

        # Count CJK characters
        cjk = sum(1 for c in text if '一' <= c <= '鿿' or '㐀' <= c <= '䶿')
        # Count ASCII letters
        ascii_alpha = sum(1 for c in text if c.isascii() and c.isalpha())
        total_alpha = cjk + ascii_alpha

        if total_alpha == 0:
            return False

        if target_lang == "zh_CN":
            return cjk / total_alpha < threshold
        elif target_lang == "en_US":
            return ascii_alpha / total_alpha < threshold

        return False

    @staticmethod
    def case_needs_translation(
        case: dict,
        target_lang: str,
        threshold: float = 0.5,
    ) -> List[str]:
        """检测单个用例中哪些字段需要翻译。

        Detect which fields in a case dict need translation.
        Returns a list of field names that need translation.
        """
        fields = []
        for field in _TRANSLATABLE_FIELDS:
            value = case.get(field)
            if isinstance(value, str) and CaseTranslator.needs_translation(
                value, target_lang, threshold
            ):
                fields.append(field)
        # 对于业务链路，也检查每个 step / For biz flows, also check each step
        if case.get("case_type") == "biz":
            for step in case.get("steps", []):
                if isinstance(step, dict):
                    for field in _TRANSLATABLE_FIELDS:
                        value = step.get(field)
                        if isinstance(value, str) and CaseTranslator.needs_translation(
                            value, target_lang, threshold
                        ):
                            if field not in fields:
                                fields.append(field)
        return fields

    # ------------------------------------------------------------------
    # 批量翻译 / Batch translation
    # ------------------------------------------------------------------

    def translate_batch(self, cases: List[dict]) -> List[dict]:
        """翻译一批用例。

        Translate a batch of test cases. Uses JSON as intermediate format.
        After LLM returns translated cases, restores all protected fields
        from the original data to prevent accidental modification.

        Args:
            cases: 用例 dict 列表 / List of case dicts.

        Returns:
            翻译后的用例列表（同顺序）/ Translated cases in same order.
        """
        # 序列化为 JSON / Serialize to JSON
        cases_json = json.dumps(cases, ensure_ascii=False, indent=2)

        # 渲染 prompt / Render prompts
        lang_name = self._language_display()
        system_msg = render_prompt(TRANSLATOR_SYSTEM, target_language=lang_name)
        user_msg = render_prompt(
            TRANSLATOR_USER,
            target_language=lang_name,
            cases_json=cases_json,
        )

        # 调用 LLM（JSON mode）/ Call LLM with JSON mode
        raw_response = self.call_llm(user_msg, system_msg, response_format="json_object")

        # 解析响应 / Parse response
        try:
            translated = self._extract_json(raw_response)
        except ValueError:
            logger.warning(
                "Failed to parse translator LLM response as JSON, len=%d", len(raw_response)
            )
            # 返回原始数据作为回退 / Return original data as fallback
            return cases

        # 确保返回数组 / Ensure we got an array
        if isinstance(translated, dict):
            # 可能 LLM 返回的是 {"cases": [...]} 之类的包装 / LLM may wrap in a dict
            for val in translated.values():
                if isinstance(val, list):
                    translated = val
                    break
            else:
                logger.warning("Translator returned a dict instead of array, using original")
                return cases

        if not isinstance(translated, list):
            logger.warning("Translator returned non-list: %s", type(translated).__name__)
            return cases

        # 长度不匹配时回退 / Fallback on length mismatch
        if len(translated) != len(cases):
            logger.warning(
                "Translator returned %d cases but expected %d, using original",
                len(translated), len(cases),
            )
            return cases

        # 字段级保护：从原始数据恢复所有非翻译字段
        # Field-level protection: restore all protected fields from original
        for i, (original, result) in enumerate(zip(cases, translated)):
            for field in _PROTECTED_FIELDS:
                if field in original:
                    result[field] = original[field]
            # 对业务链路步骤也做字段保护 / Also protect biz flow step fields
            if result.get("case_type") == "biz":
                orig_steps = original.get("steps", [])
                result_steps = result.get("steps", [])
                if isinstance(orig_steps, list) and isinstance(result_steps, list):
                    for j, (orig_step, res_step) in enumerate(zip(orig_steps, result_steps)):
                        if isinstance(orig_step, dict) and isinstance(res_step, dict):
                            for field in _PROTECTED_FIELDS:
                                if field in orig_step:
                                    res_step[field] = orig_step[field]
                    # 如果步数不匹配，恢复原始步数 / Restore original steps if count mismatch
                    if len(result_steps) != len(orig_steps):
                        result["steps"] = orig_steps

        return translated
