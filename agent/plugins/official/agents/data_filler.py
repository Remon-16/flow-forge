"""Data fillers: fill request data into test case skeletons.
数据填充器：为测试用例骨架填充请求数据。
"""

import json
import logging
from typing import Any, Dict, List, Optional

from agents.base import BaseAgent
from agents.skeleton_generator import _count_validate
from config.settings import Settings, get_strategy
from knowledge.search import KnowledgeSearch
from prompts import KNOWLEDGE_SECTION_HEADER
from plugins.official.prompts.data_filling import (
    SINGLE_DATA_FILLING_SYSTEM,
    SINGLE_DATA_FILLING_USER,
    BIZ_DATA_FILLING_SYSTEM,
    BIZ_DATA_FILLING_USER,
)
from prompts.render import render_prompt
from i18n import _, get_language_name

logger = logging.getLogger(__name__)


class SingleDataFiller(BaseAgent):
    """为单接口测试用例骨架填充请求数据 / Fill request data for single API test case skeletons."""

    def __init__(
        self,
        settings: Settings,
        knowledge: Optional[KnowledgeSearch] = None,
        skill_extensions=None,
        case_gen_rules: Optional[List[Dict]] = None,
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
        self._case_gen_rules = (
            case_gen_rules if case_gen_rules is not None
            else getattr(settings, "case_gen_rules", [])
        )
        # 用例格式校验重试次数 / Case format validation retry count
        self._case_format_max_retries = getattr(settings, "case_format_max_retries", 3)

    def fill_batch(
        self,
        skeletons: List[Dict],
        interfaces: List[Any],
        api_summary: Optional[List[Dict]] = None,
        api_doc_text: str = "",
        user_guidance: str = "",
        previous_errors: Optional[List[Dict]] = None,
    ) -> List[Dict]:
        """Fill request data for a batch of single case skeletons.

        Uses pre-search against API doc text to provide relevant snippets
        instead of truncated full text.
        """
        api_summary_str = json.dumps(api_summary or [], ensure_ascii=False, indent=2)

        # Filter interfaces relevant to this batch
        relevant_ids = {s.get("relevance_id", "") for s in skeletons}
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
                    "request_head": getattr(item, "request_head", {}),
                    "request_body": getattr(item, "request_body", {}),
                })

        # Build relevant doc snippets via pre-search
        doc_snippets = ""
        if api_doc_text:
            snippets_list = []
            for skeleton in skeletons:
                relevance_id = skeleton.get("relevance_id", "")
                http_method = skeleton.get("method", "GET")
                # Find correct interface
                correct_url = ""
                for iface in iface_dicts:
                    if iface.get("test_id") == relevance_id:
                        correct_url = iface.get("url", "")
                        break
                if correct_url:
                    snippet = self._fuzzy_search_api_doc(
                        url=correct_url, http_method=http_method,
                        api_doc_text=api_doc_text, max_snippet_tokens=2000,
                    )
                else:
                    # Fuzzy match fallback
                    matched = self._fuzzy_match_interface(
                        url=skeleton.get("url", ""),
                        api_name=skeleton.get("api_name", ""),
                        http_method=http_method,
                        interfaces=iface_dicts,
                    )
                    search_url = matched.get("url", "") if matched else skeleton.get("url", "")
                    snippet = self._fuzzy_search_api_doc(
                        url=search_url, http_method=http_method,
                        api_doc_text=api_doc_text, max_snippet_tokens=2000,
                    )
                if snippet:
                    snippets_list.append(snippet)
            doc_snippets = "\n---\n".join(snippets_list) if snippets_list else "(none)"

        error_context = ""
        if previous_errors:
            error_context = (
                "\n\n## Previous generation validation failed, please fix the following issues\n"
                + json.dumps(previous_errors, ensure_ascii=False, indent=2)
                + "\nPlease ensure JSON format is correct and all required fields are complete."
            )

        prompt = render_prompt(
            SINGLE_DATA_FILLING_USER,
            skeletons=json.dumps(skeletons, ensure_ascii=False, indent=2),
            interface_defs=json.dumps(iface_dicts, ensure_ascii=False, indent=2),
            api_summary=api_summary_str,
            api_doc_text=doc_snippets,
            user_guidance=user_guidance or "(none)",
            language=get_language_name(),
        )
        prompt += error_context

        if self._knowledge is not None:
            docs = self._knowledge.search("request data filling test case", n_results=3)
            if docs:
                prompt += f"\n\n{KNOWLEDGE_SECTION_HEADER}" + "\n---\n".join(docs)

        logger.info(_("plugin.data_fill.single", count=len(skeletons)))
        expected_count = len(skeletons)
        return _count_validate(
            self, prompt, SINGLE_DATA_FILLING_SYSTEM,
            "cases", expected_count, "single data fill",
            get_strategy(self._case_gen_rules, "data_fill_count"),
            max_retries=self._case_format_max_retries,
        )


class BizDataFiller(BaseAgent):
    """为业务链路测试用例骨架填充请求数据和继承字段。
    Fill request data and Inherit fields for business flow test case skeletons.
    """

    def __init__(
        self,
        settings: Settings,
        knowledge: Optional[KnowledgeSearch] = None,
        skill_extensions=None,
        case_gen_rules: Optional[List[Dict]] = None,
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
        self._case_gen_rules = (
            case_gen_rules if case_gen_rules is not None
            else getattr(settings, "case_gen_rules", [])
        )
        # 用例格式校验重试次数 / Case format validation retry count
        self._case_format_max_retries = getattr(settings, "case_format_max_retries", 3)

    def fill_batch(
        self,
        skeletons: List[Dict],
        interfaces: List[Any],
        api_summary: Optional[List[Dict]] = None,
        api_doc_text: str = "",
        user_guidance: str = "",
        previous_errors: Optional[List[Dict]] = None,
    ) -> List[Dict]:
        """Fill request data and Inherit for a batch of biz flow skeletons.

        Uses pre-search against API doc text to provide relevant snippets.
        """
        api_summary_str = json.dumps(api_summary or [], ensure_ascii=False, indent=2)

        # Collect all relevance_ids from all steps
        relevant_ids = set()
        for flow in skeletons:
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
                    "request_head": getattr(item, "request_head", {}),
                    "request_body": getattr(item, "request_body", {}),
                })

        # Build relevant doc snippets via pre-search
        doc_snippets = ""
        if api_doc_text:
            snippets_list = []
            for flow in skeletons:
                for step in flow.get("steps", []):
                    relevance_id = step.get("relevance_id", "")
                    http_method = step.get("method", "GET")
                    correct_url = ""
                    for iface in iface_dicts:
                        if iface.get("test_id") == relevance_id:
                            correct_url = iface.get("url", "")
                            break
                    if correct_url:
                        snippet = self._fuzzy_search_api_doc(
                            url=correct_url, http_method=http_method,
                            api_doc_text=api_doc_text, max_snippet_tokens=2000,
                        )
                    else:
                        matched = self._fuzzy_match_interface(
                            url=step.get("url", ""),
                            api_name=step.get("api_name", ""),
                            http_method=http_method,
                            interfaces=iface_dicts,
                        )
                        search_url = matched.get("url", "") if matched else step.get("url", "")
                        snippet = self._fuzzy_search_api_doc(
                            url=search_url, http_method=http_method,
                            api_doc_text=api_doc_text, max_snippet_tokens=2000,
                        )
                    if snippet:
                        snippets_list.append(snippet)
            doc_snippets = "\n---\n".join(snippets_list) if snippets_list else "(none)"

        error_context = ""
        if previous_errors:
            error_context = (
                "\n\n## Previous generation validation failed, please fix the following issues\n"
                + json.dumps(previous_errors, ensure_ascii=False, indent=2)
                + "\nPlease ensure JSON format is correct and all required fields are complete."
            )

        prompt = render_prompt(
            BIZ_DATA_FILLING_USER,
            skeletons=json.dumps(skeletons, ensure_ascii=False, indent=2),
            interface_defs=json.dumps(iface_dicts, ensure_ascii=False, indent=2),
            api_summary=api_summary_str,
            api_doc_text=doc_snippets,
            user_guidance=user_guidance or "(none)",
            language=get_language_name(),
        )
        prompt += error_context

        if self._knowledge is not None:
            docs = self._knowledge.search("business flow inherit data dependency", n_results=3)
            if docs:
                prompt += f"\n\n{KNOWLEDGE_SECTION_HEADER}" + "\n---\n".join(docs)

        logger.info(_("plugin.data_fill.biz", count=len(skeletons)))
        expected_count = len(skeletons)
        return _count_validate(
            self, prompt, BIZ_DATA_FILLING_SYSTEM,
            "biz_flows", expected_count, "biz data fill",
            get_strategy(self._case_gen_rules, "data_fill_count"),
            max_retries=self._case_format_max_retries,
        )
