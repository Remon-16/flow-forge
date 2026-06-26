"""Skeleton generators: produce test case skeletons for single and biz flow cases."""

import json
import logging
from typing import Any, Dict, List, Optional

from .base import BaseAgent
from config.settings import Settings
from knowledge.search import KnowledgeSearch
from prompts import KNOWLEDGE_SECTION_HEADER
from prompts.skeleton_generation import (
    SINGLE_SKELETON_SYSTEM,
    SINGLE_SKELETON_USER,
    BIZ_SKELETON_SYSTEM,
    BIZ_SKELETON_USER,
    URL_CORRECTION_SYSTEM,
    URL_CORRECTION_USER,
)
from prompts.render import render_prompt
from i18n import get_language_name

logger = logging.getLogger(__name__)


def _serialize_plan_single(plan) -> str:
    """Serialize single test points from plan for prompt."""
    parts = []
    if hasattr(plan, "business_summary") and plan.business_summary:
        parts.append(f"## Business Understanding\n{plan.business_summary}")
    if hasattr(plan, "single_test_points") and plan.single_test_points:
        parts.append("\n## Single API Test Points")
        for api_id, points in plan.single_test_points.items():
            parts.append(f"\n### {api_id}")
            for p in points:
                parts.append(
                    f"- [{p.tag}] {p.test_id}: {p.description} ({p.scenario_type})"
                )
    return "\n".join(parts)


def _serialize_plan_biz(plan) -> str:
    """Serialize biz flow scenarios from plan for prompt."""
    parts = []
    if hasattr(plan, "business_summary") and plan.business_summary:
        parts.append(f"## Business Understanding\n{plan.business_summary}")
    if hasattr(plan, "biz_flow_scenarios") and plan.biz_flow_scenarios:
        parts.append("\n## Business Flow Scenarios")
        for scenario in plan.biz_flow_scenarios:
            parts.append(
                f"- {scenario.get('name', '')}: {scenario.get('description', '')}"
            )
    if hasattr(plan, "mermaid_flows") and plan.mermaid_flows:
        parts.append("\n## Business Flow Diagrams")
        for name, diagram in plan.mermaid_flows.items():
            parts.append(f"\n### {name}\n```mermaid\n{diagram}\n```")
    return "\n".join(parts)


def _normalize_interfaces(items: List[Any]) -> List[Dict[str, Any]]:
    """Convert mixed InterfaceDef/dicts to unified list of dicts."""
    result = []
    for item in items:
        if isinstance(item, dict):
            result.append({
                "test_id": item.get("test_id", ""),
                "api_name": item.get("api_name", item.get("name", "")),
                "app_name": item.get("app_name", item.get("app", "")),
                "method": item.get("method", "GET"),
                "url": item.get("url", ""),
            })
        elif hasattr(item, "test_id"):
            result.append({
                "test_id": item.test_id,
                "api_name": item.api_name,
                "app_name": item.app_name,
                "method": item.method,
                "url": item.url,
            })
    return result


class SingleSkeletonGenerator(BaseAgent):
    """Generate single API test case skeletons in one shot."""

    def __init__(self, settings: Settings, knowledge: Optional[KnowledgeSearch] = None, skill_extensions: List[str] = None):
        super().__init__(
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            max_retries=settings.max_retries,
            max_steps=settings.max_steps,
            base_url=settings.llm_base_url,
            context_window=settings.llm_context_window,
            max_output_tokens=settings.llm_max_output_tokens,
            compression_threshold=settings.llm_context_compression_threshold,
            skill_extensions=skill_extensions,
        )
        self._knowledge = knowledge

    def generate(
        self,
        plan,
        interfaces: List[Any],
        api_summary: Optional[List[Dict]] = None,
        user_guidance: str = "",
    ) -> List[Dict]:
        """Generate all single API case skeletons at once."""
        plan_str = _serialize_plan_single(plan)
        iface_dicts = _normalize_interfaces(interfaces)
        api_summary_str = json.dumps(api_summary or [], ensure_ascii=False, indent=2)

        prompt = render_prompt(
            SINGLE_SKELETON_USER,
            test_plan=plan_str,
            interface_defs=json.dumps(iface_dicts, ensure_ascii=False, indent=2),
            api_summary=api_summary_str,
            user_guidance=user_guidance or "(none)",
            language=get_language_name(),
        )

        if self._knowledge is not None:
            docs = self._knowledge.search("test case skeleton", n_results=3)
            if docs:
                prompt += f"\n\n{KNOWLEDGE_SECTION_HEADER}" + "\n---\n".join(docs)

        # Compute expected skeleton count from plan
        expected_count = sum(len(points) for points in plan.single_test_points.values()) \
            if hasattr(plan, "single_test_points") and plan.single_test_points else 0
        if expected_count == 0:
            logger.info("No single test points in plan, skipping")
            return []

        # Token check
        input_tokens = self._estimate_input_tokens(SINGLE_SKELETON_SYSTEM, prompt)
        if input_tokens > self._context_window:
            raise ValueError(
                f"Skeleton generation input exceeds context window: "
                f"{input_tokens} / {self._context_window} tokens"
            )

        logger.info("Generating %d single case skeletons (~%d tokens)...", expected_count, input_tokens)
        for attempt in range(self._max_retries + 1):
            result = self.call_llm_json(prompt, SINGLE_SKELETON_SYSTEM)
            skeletons = result.get("single_skeletons", [])
            if len(skeletons) == expected_count:
                logger.info("Generated %d single case skeletons", len(skeletons))
                return skeletons
            logger.warning(
                "Single skeleton count mismatch attempt %d/%d: expected %d, got %d",
                attempt + 1, self._max_retries + 1, expected_count, len(skeletons),
            )
        raise ValueError(
            f"Single skeleton count validation failed after {self._max_retries + 1} "
            f"attempts: expected {expected_count}, got {len(skeletons)}"
        )

    def correct_urls(
        self,
        bad_cases: List[Dict],
        interfaces: List[Any],
        api_doc_text: str,
        api_summary: Optional[List[Dict]] = None,
    ) -> List[Dict]:
        """Correct URLs using trusted interfaces + API doc pre-search.

        Interfaces are assumed to have passed source validation
        (validate_interface_urls_node + user review + reload).
        """
        iface_dicts = _normalize_interfaces(interfaces)

        # Build search snippets per bad case
        snippets_parts = []
        for case in bad_cases:
            relevance_id = case.get("relevance_id", "")
            bad_url = case.get("url", "")
            api_name = case.get("api_name", "")
            http_method = case.get("method", "GET")

            # Look up correct URL from trusted interfaces
            correct_iface = None
            for iface in iface_dicts:
                if iface.get("test_id") == relevance_id:
                    correct_iface = iface
                    break

            if correct_iface:
                correct_url = correct_iface.get("url", "")
                snippet = self._fuzzy_search_api_doc(
                    url=correct_url, http_method=http_method,
                    api_doc_text=api_doc_text, max_snippet_tokens=2000,
                )
            else:
                # Fuzzy match in interfaces, then search
                matched = self._fuzzy_match_interface(
                    url=bad_url, api_name=api_name,
                    http_method=http_method, interfaces=iface_dicts,
                )
                if matched:
                    snippet = self._fuzzy_search_api_doc(
                        url=matched.get("url", ""), http_method=http_method,
                        api_doc_text=api_doc_text, max_snippet_tokens=2000,
                    )
                else:
                    snippet = self._fuzzy_search_api_doc(
                        url=bad_url, http_method=http_method,
                        api_doc_text=api_doc_text, max_snippet_tokens=2000,
                    )

            snippets_parts.append(
                f"### Case: {case.get('test_id', '?')}\n"
                f"Current URL: {bad_url}\n"
                f"Relevant API doc:\n{snippet}"
            )

        prompt = URL_CORRECTION_USER.replace(
            "{{bad_cases}}",
            json.dumps(bad_cases, ensure_ascii=False, indent=2),
        ).replace(
            "{{api_doc_text}}", "\n---\n".join(snippets_parts)
        ).replace(
            "{{interface_defs}}",
            json.dumps(iface_dicts, ensure_ascii=False, indent=2),
        )

        logger.info("Correcting URLs for %d cases...", len(bad_cases))
        expected_count = len(bad_cases)
        for attempt in range(self._max_retries + 1):
            result = self.call_llm_json(prompt, URL_CORRECTION_SYSTEM)
            corrected = result.get("cases") or result.get("single_skeletons") or []
            if not corrected:
                if isinstance(result, list):
                    corrected = result
            if not corrected:
                logger.warning("URL correction returned empty result, attempt %d/%d",
                               attempt + 1, self._max_retries + 1)
                continue
            if len(corrected) == expected_count:
                return corrected
            logger.warning(
                "URL correction count mismatch attempt %d/%d: expected %d, got %d",
                attempt + 1, self._max_retries + 1, expected_count, len(corrected),
            )
        logger.warning("URL correction count validation failed after %d attempts, "
                       "falling back to original bad_cases", self._max_retries + 1)
        return bad_cases


class BizSkeletonGenerator(BaseAgent):
    """Generate business flow test case skeletons in one shot."""

    def __init__(self, settings: Settings, knowledge: Optional[KnowledgeSearch] = None, skill_extensions: List[str] = None):
        super().__init__(
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            max_retries=settings.max_retries,
            max_steps=settings.max_steps,
            base_url=settings.llm_base_url,
            context_window=settings.llm_context_window,
            max_output_tokens=settings.llm_max_output_tokens,
            compression_threshold=settings.llm_context_compression_threshold,
            skill_extensions=skill_extensions,
        )
        self._knowledge = knowledge

    def generate(
        self,
        plan,
        interfaces: List[Any],
        api_summary: Optional[List[Dict]] = None,
        user_guidance: str = "",
    ) -> List[Dict]:
        """Generate all biz flow case skeletons at once."""
        plan_str = _serialize_plan_biz(plan)
        iface_dicts = _normalize_interfaces(interfaces)
        api_summary_str = json.dumps(api_summary or [], ensure_ascii=False, indent=2)

        # Skip if no biz flow scenarios
        if not (hasattr(plan, "biz_flow_scenarios") and plan.biz_flow_scenarios):
            logger.info("No biz flow scenarios in plan, skipping biz skeleton generation")
            return []

        prompt = render_prompt(
            BIZ_SKELETON_USER,
            test_plan=plan_str,
            interface_defs=json.dumps(iface_dicts, ensure_ascii=False, indent=2),
            api_summary=api_summary_str,
            user_guidance=user_guidance or "(none)",
            language=get_language_name(),
        )

        if self._knowledge is not None:
            docs = self._knowledge.search("business flow test case", n_results=3)
            if docs:
                prompt += f"\n\n{KNOWLEDGE_SECTION_HEADER}" + "\n---\n".join(docs)

        expected_count = len(plan.biz_flow_scenarios)

        # Token check
        input_tokens = self._estimate_input_tokens(BIZ_SKELETON_SYSTEM, prompt)
        if input_tokens > self._context_window:
            raise ValueError(
                f"Biz skeleton generation input exceeds context window: "
                f"{input_tokens} / {self._context_window} tokens"
            )

        logger.info("Generating %d biz flow skeletons (~%d tokens)...", expected_count, input_tokens)
        for attempt in range(self._max_retries + 1):
            result = self.call_llm_json(prompt, BIZ_SKELETON_SYSTEM)
            skeletons = result.get("biz_skeletons", [])
            if len(skeletons) == expected_count:
                logger.info("Generated %d biz flow skeletons", len(skeletons))
                return skeletons
            logger.warning(
                "Biz skeleton count mismatch attempt %d/%d: expected %d, got %d",
                attempt + 1, self._max_retries + 1, expected_count, len(skeletons),
            )
        raise ValueError(
            f"Biz skeleton count validation failed after {self._max_retries + 1} "
            f"attempts: expected {expected_count}, got {len(skeletons)}"
        )

    def correct_urls(
        self,
        bad_cases: List[Dict],
        interfaces: List[Any],
        api_doc_text: str,
        api_summary: Optional[List[Dict]] = None,
    ) -> List[Dict]:
        """Correct URLs using trusted interfaces + API doc pre-search."""
        iface_dicts = _normalize_interfaces(interfaces)

        # Build search snippets per bad case
        snippets_parts = []
        for case in bad_cases:
            # For biz flows, check each step's URL
            steps = case.get("steps", [])
            for step in steps:
                relevance_id = step.get("relevance_id", "")
                bad_url = step.get("url", "")
                api_name = step.get("api_name", "")
                http_method = step.get("method", "GET")

                correct_iface = None
                for iface in iface_dicts:
                    if iface.get("test_id") == relevance_id:
                        correct_iface = iface
                        break

                if correct_iface:
                    correct_url = correct_iface.get("url", "")
                    snippet = self._fuzzy_search_api_doc(
                        url=correct_url, http_method=http_method,
                        api_doc_text=api_doc_text, max_snippet_tokens=2000,
                    )
                else:
                    matched = self._fuzzy_match_interface(
                        url=bad_url, api_name=api_name,
                        http_method=http_method, interfaces=iface_dicts,
                    )
                    if matched:
                        snippet = self._fuzzy_search_api_doc(
                            url=matched.get("url", ""), http_method=http_method,
                            api_doc_text=api_doc_text, max_snippet_tokens=2000,
                        )
                    else:
                        snippet = self._fuzzy_search_api_doc(
                            url=bad_url, http_method=http_method,
                            api_doc_text=api_doc_text, max_snippet_tokens=2000,
                        )

                snippets_parts.append(
                    f"### Step: {step.get('step_id', '?')}\n"
                    f"Current URL: {bad_url}\n"
                    f"Relevant API doc:\n{snippet}"
                )

        prompt = URL_CORRECTION_USER.replace(
            "{{bad_cases}}",
            json.dumps(bad_cases, ensure_ascii=False, indent=2),
        ).replace(
            "{{api_doc_text}}", "\n---\n".join(snippets_parts)
        ).replace(
            "{{interface_defs}}",
            json.dumps(iface_dicts, ensure_ascii=False, indent=2),
        )

        logger.info("Correcting URLs for %d biz flow cases...", len(bad_cases))
        expected_count = len(bad_cases)
        for attempt in range(self._max_retries + 1):
            result = self.call_llm_json(prompt, URL_CORRECTION_SYSTEM)
            corrected = result.get("cases") or result.get("biz_skeletons") or result.get("biz_flows") or []
            if not corrected:
                if isinstance(result, list):
                    corrected = result
            if not corrected:
                logger.warning("Biz URL correction returned empty result, attempt %d/%d",
                               attempt + 1, self._max_retries + 1)
                continue
            if len(corrected) == expected_count:
                return corrected
            logger.warning(
                "Biz URL correction count mismatch attempt %d/%d: expected %d, got %d",
                attempt + 1, self._max_retries + 1, expected_count, len(corrected),
            )
        logger.warning("Biz URL correction count validation failed after %d attempts, "
                       "falling back to original bad_cases", self._max_retries + 1)
        return bad_cases
