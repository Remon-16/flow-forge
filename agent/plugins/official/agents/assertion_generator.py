"""Assertion generators: generate assert_dict and assert_rules for test cases.
断言生成器：为测试用例生成断言字典和断言规则。
"""

import json
import logging
from typing import Any, Dict, List, Optional

from agents.base import BaseAgent
from utils.count_validate import count_validate as _count_validate
from config.settings import Settings, get_strategy
from knowledge.search import KnowledgeSearch
from prompts import KNOWLEDGE_SECTION_HEADER
from plugins.official.prompts.assertion_generation import (
    SINGLE_ASSERTION_SYSTEM,
    SINGLE_ASSERTION_USER,
    BIZ_ASSERTION_SYSTEM,
    BIZ_ASSERTION_USER,
)
from prompts.render import render_prompt
from i18n import _, get_language_name

logger = logging.getLogger(__name__)


class SingleAssertionGenerator(BaseAgent):
    """为单接口测试用例生成断言 / Generate assertions for single API test cases."""

    def __init__(
        self,
        settings: Settings,
        knowledge: Optional[KnowledgeSearch] = None,
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
        self._knowledge = knowledge
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
        """Generate assertions for a batch of single API cases."""
        api_summary_str = json.dumps(api_summary or [], ensure_ascii=False, indent=2)

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
            elif hasattr(item, "test_id"):
                iface_dicts.append({
                    "test_id": item.test_id,
                    "api_name": item.api_name,
                    "method": item.method,
                    "url": item.url,
                    "status_code": getattr(item, "status_code", 200),
                    "response_summary": getattr(item, "_response_summary", ""),
                })

        # Also include response_summary from api_summary
        if api_summary:
            for isum in api_summary:
                if isinstance(isum, dict) and isum.get("response_summary"):
                    for iface in iface_dicts:
                        if iface.get("test_id") == isum.get("api_path") or \
                           iface.get("test_id") == isum.get("test_id"):
                            iface["response_summary"] = isum.get("response_summary", "")

        error_context = ""
        if previous_errors:
            error_context = (
                "\n\n## Previous generation validation failed, please fix the following issues\n"
                + json.dumps(previous_errors, ensure_ascii=False, indent=2)
            )

        prompt = render_prompt(
            SINGLE_ASSERTION_USER,
            cases=json.dumps(cases, ensure_ascii=False, indent=2),
            interface_defs=json.dumps(iface_dicts, ensure_ascii=False, indent=2),
            api_summary=api_summary_str,
            user_guidance=user_guidance or "(none)",
            language=get_language_name(),
        )
        prompt += error_context

        if self._knowledge is not None:
            docs = self._knowledge.search("assertion test case", n_results=3)
            if docs:
                prompt += f"\n\n{KNOWLEDGE_SECTION_HEADER}" + "\n---\n".join(docs)

        logger.info(_("plugin.assertion_gen.single", count=len(cases)))
        expected_count = len(cases)
        return _count_validate(
            self, prompt, SINGLE_ASSERTION_SYSTEM,
            "cases", expected_count, "single assertion",
            get_strategy(self._case_gen_validation, "assertion_count"),
            max_retries=self._case_format_max_retries,
        )


class BizAssertionGenerator(BaseAgent):
    """为业务链路测试用例生成断言 / Generate assertions for business flow test cases."""

    def __init__(
        self,
        settings: Settings,
        knowledge: Optional[KnowledgeSearch] = None,
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
        self._knowledge = knowledge
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
        """Generate assertions for a batch of biz flow cases."""
        api_summary_str = json.dumps(api_summary or [], ensure_ascii=False, indent=2)

        # Collect all relevance_ids from all steps
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
            elif hasattr(item, "test_id"):
                iface_dicts.append({
                    "test_id": item.test_id,
                    "api_name": item.api_name,
                    "method": item.method,
                    "url": item.url,
                    "status_code": getattr(item, "status_code", 200),
                })

        # Include response_summary from api_summary
        if api_summary:
            for isum in api_summary:
                if isinstance(isum, dict) and isum.get("response_summary"):
                    for iface in iface_dicts:
                        if iface.get("test_id") == isum.get("api_path") or \
                           iface.get("test_id") == isum.get("test_id"):
                            iface["response_summary"] = isum.get("response_summary", "")

        error_context = ""
        if previous_errors:
            error_context = (
                "\n\n## Previous generation validation failed, please fix the following issues\n"
                + json.dumps(previous_errors, ensure_ascii=False, indent=2)
            )

        prompt = render_prompt(
            BIZ_ASSERTION_USER,
            cases=json.dumps(cases, ensure_ascii=False, indent=2),
            interface_defs=json.dumps(iface_dicts, ensure_ascii=False, indent=2),
            api_summary=api_summary_str,
            user_guidance=user_guidance or "(none)",
            language=get_language_name(),
        )
        prompt += error_context

        if self._knowledge is not None:
            docs = self._knowledge.search("business flow assertion", n_results=3)
            if docs:
                prompt += f"\n\n{KNOWLEDGE_SECTION_HEADER}" + "\n---\n".join(docs)

        logger.info(_("plugin.assertion_gen.biz", count=len(cases)))
        expected_count = len(cases)
        return _count_validate(
            self, prompt, BIZ_ASSERTION_SYSTEM,
            "biz_flows", expected_count, "biz assertion",
            get_strategy(self._case_gen_validation, "assertion_count"),
            max_retries=self._case_format_max_retries,
        )
