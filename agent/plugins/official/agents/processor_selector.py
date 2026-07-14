"""处理器选择器：为测试用例分配前置/后置处理器。
Processor selector: assigns pre/post-processors to test cases.

根据已填充数据的用例和接口定义，由 LLM 决定哪些 DB 处理器应被添加。
Based on data-filled cases and interface definitions, the LLM decides which
DB processors to assign to each case.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from agents.base import BaseAgent
from agents.skeleton_generator import _count_validate
from config.settings import Settings, get_strategy
from plugins.official.prompts.processor_selection import (
    SINGLE_PROCESSOR_SYSTEM,
    SINGLE_PROCESSOR_USER,
    BIZ_PROCESSOR_SYSTEM,
    BIZ_PROCESSOR_USER,
)
from prompts.render import render_prompt
from i18n import _, get_language_name

logger = logging.getLogger(__name__)


class SingleProcessorSelector(BaseAgent):
    """为单接口测试用例分配处理器 / Assign processors to single API test cases."""

    def __init__(
        self,
        settings: Settings,
        knowledge=None,
        skill_extensions=None,
        case_gen_validation: Optional[List[Dict]] = None,
    ):
        super().__init__(
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            max_retries=settings.max_retries,
            max_steps=settings.max_steps,
            base_url=settings.llm_base_url,
            context_window=settings.llm_context_window,
            max_output_tokens=settings.llm_max_output_tokens,
            compression_threshold=settings.llm_context_compression_threshold,
            skill_extensions=skill_extensions,
        )
        # 校验规则列表（优先用传入参数，否则从 settings 取）
        # Validation rules list (use explicit param first, fallback to settings)
        self._case_gen_validation = (
            case_gen_validation if case_gen_validation is not None
            else getattr(settings, "case_gen_validation", [])
        )
        # 用例格式校验重试次数 / Case format validation retry count
        self._case_format_max_retries = getattr(settings, "case_format_max_retries", 3)

    def fill_batch(
        self,
        cases: List[Dict],
        interfaces: List[Any],
        api_summary: Optional[List[Dict]] = None,
        user_guidance: str = "",
        previous_errors: Optional[List[Dict]] = None,
    ) -> List[Dict]:
        """为本批单接口用例分配处理器 / Assign processors for a batch of single cases."""

        # 筛选与本批用例相关的接口定义
        # Filter interfaces relevant to this batch
        relevant_ids = {c.get("relevance_id", "") for c in cases}
        relevant_ifaces = [
            i for i in interfaces
            if (isinstance(i, dict) and i.get("test_id") in relevant_ids)
            or (hasattr(i, "test_id") and i.test_id in relevant_ids)
        ]
        iface_dicts = []
        for item in relevant_ifaces:
            if isinstance(item, dict):
                iface_dicts.append(item)

        # 构建错误上下文（重试时附加）
        # Build error context (appended on retry)
        error_context = ""
        if previous_errors:
            error_context = (
                "\n\n## Previous generation validation failed, please fix the following issues\n"
                + json.dumps(previous_errors, ensure_ascii=False, indent=2)
                + "\nPlease ensure JSON format is correct and all required fields are complete."
            )

        prompt = render_prompt(
            SINGLE_PROCESSOR_USER,
            cases=json.dumps(cases, ensure_ascii=False, indent=2),
            interface_defs=json.dumps(iface_dicts, ensure_ascii=False, indent=2),
            api_summary=json.dumps(api_summary or [], ensure_ascii=False, indent=2),
            user_guidance=user_guidance or "(none)",
            language=get_language_name(),
        )
        prompt += error_context

        logger.info(
            _("plugin.processor_selection.single", count=len(cases)),
        )
        expected_count = len(cases)
        return _count_validate(
            self, prompt, SINGLE_PROCESSOR_SYSTEM,
            "cases", expected_count, "processor selection (single)",
            get_strategy(self._case_gen_validation, "processor_count"),
            max_retries=self._case_format_max_retries,
        )


class BizProcessorSelector(BaseAgent):
    """为业务链路测试用例分配处理器 / Assign processors to biz flow test cases."""

    def __init__(
        self,
        settings: Settings,
        knowledge=None,
        skill_extensions=None,
        case_gen_validation: Optional[List[Dict]] = None,
    ):
        super().__init__(
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            max_retries=settings.max_retries,
            max_steps=settings.max_steps,
            base_url=settings.llm_base_url,
            context_window=settings.llm_context_window,
            max_output_tokens=settings.llm_max_output_tokens,
            compression_threshold=settings.llm_context_compression_threshold,
            skill_extensions=skill_extensions,
        )
        self._case_gen_validation = (
            case_gen_validation if case_gen_validation is not None
            else getattr(settings, "case_gen_validation", [])
        )
        self._case_format_max_retries = getattr(settings, "case_format_max_retries", 3)

    def fill_batch(
        self,
        cases: List[Dict],
        interfaces: List[Any],
        api_summary: Optional[List[Dict]] = None,
        user_guidance: str = "",
        previous_errors: Optional[List[Dict]] = None,
    ) -> List[Dict]:
        """为本批业务流用例分配处理器 / Assign processors for a batch of biz flow cases."""

        # 筛选相关接口 / Filter relevant interfaces
        relevant_ids = set()
        for flow in cases:
            for step in flow.get("steps", []):
                rid = step.get("relevance_id", "")
                if rid:
                    relevant_ids.add(rid)

        relevant_ifaces = [
            i for i in interfaces
            if (isinstance(i, dict) and i.get("test_id") in relevant_ids)
            or (hasattr(i, "test_id") and i.test_id in relevant_ids)
        ]
        iface_dicts = []
        for item in relevant_ifaces:
            if isinstance(item, dict):
                iface_dicts.append(item)

        error_context = ""
        if previous_errors:
            error_context = (
                "\n\n## Previous generation validation failed, please fix the following issues\n"
                + json.dumps(previous_errors, ensure_ascii=False, indent=2)
                + "\nPlease ensure JSON format is correct and all required fields are complete."
            )

        prompt = render_prompt(
            BIZ_PROCESSOR_USER,
            cases=json.dumps(cases, ensure_ascii=False, indent=2),
            interface_defs=json.dumps(iface_dicts, ensure_ascii=False, indent=2),
            api_summary=json.dumps(api_summary or [], ensure_ascii=False, indent=2),
            user_guidance=user_guidance or "(none)",
            language=get_language_name(),
        )
        prompt += error_context

        logger.info(
            _("plugin.processor_selection.biz", count=len(cases)),
        )
        expected_count = len(cases)
        return _count_validate(
            self, prompt, BIZ_PROCESSOR_SYSTEM,
            "biz_flows", expected_count, "processor selection (biz)",
            get_strategy(self._case_gen_validation, "processor_count"),
            max_retries=self._case_format_max_retries,
        )
