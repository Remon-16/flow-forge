"""PlanParser: parse confirmed plan.md into structured TestPlan."""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from .base import BaseAgent
from config.settings import Settings
from models.schema import (
    InterfaceDef,
    PlanStep,
    TestPlan,
)

logger = logging.getLogger(__name__)


class PlanParser(BaseAgent):
    """Parse a confirmed Markdown test plan into structured TestPlan."""

    def __init__(self, settings: Settings, skill_extensions: List[str] = None):
        super().__init__(
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            temperature=0.1,
            max_retries=settings.max_retries,
            max_steps=settings.max_steps,
            base_url=settings.llm_base_url,
            context_window=settings.llm_context_window,
            max_output_tokens=settings.llm_max_output_tokens,
            compression_threshold=settings.llm_context_compression_threshold,
            skill_extensions=skill_extensions,
        )

    def parse(
        self, plan_md: str, interfaces: Optional[List[Dict[str, Any]]] = None
    ) -> TestPlan:
        """Parse plan markdown into a structured TestPlan.

        Args:
            plan_md: The plan markdown text.
            interfaces: Optional pre-validated interface definitions.  Used as
                fallback when the LLM / regex cannot extract api_definitions
                from the markdown text.
        """
        # Extract business summary (first ## section content)
        business_summary = self._extract_section(
            plan_md, r"##\s*(?:1\.)?\s*业务理解", r"##\s"
        ) or self._extract_section(plan_md, r"##\s*(?:1\.)?\s*Business", r"##\s")

        # Extract Mermaid diagrams
        mermaid_flows = self._extract_mermaid(plan_md)

        # Extract test points via LLM
        plan = self._llm_parse(plan_md)
        plan.business_summary = business_summary or plan.business_summary
        plan.mermaid_flows = mermaid_flows

        # Fallback: if LLM/regex failed to extract api_definitions,
        # use the provided interfaces (already validated)
        if not plan.api_definitions and interfaces:
            plan.api_definitions = [
                InterfaceDef(
                    test_id=iface.get("test_id", ""),
                    api_name=iface.get("api_name", ""),
                    app_name=iface.get("app_name", ""),
                    method=iface.get("method", "GET"),
                    url=iface.get("url", ""),
                )
                for iface in interfaces
            ]

        return plan

    def _llm_parse(self, plan_md: str) -> TestPlan:
        """Use LLM to extract structured test points from the plan.

        For large plans, splits by ``##`` section headers and processes
        each section independently, then merges results.
        """
        from prompts.plan_parser import (
            PLAN_PARSER_SYSTEM as system_msg,
            PLAN_PARSER_USER,
            PLAN_CHUNK_NOTICE,
        )
        from prompts.render import render_prompt

        # Check if plan fits in a single call
        test_prompt = render_prompt(PLAN_PARSER_USER, plan_md=plan_md)
        input_tokens = self._estimate_input_tokens(system_msg, test_prompt)

        if input_tokens < self._context_window * self._compression_threshold:
            try:
                result = self.call_llm_json(test_prompt, system_msg)
                return self._build_testplan(result)
            except Exception as e:
                logger.warning("LLM plan parsing failed: %s, using regex fallback", e)
                result = self._regex_parse(plan_md)
                return self._build_testplan(result)

        # Large plan — split by sections
        logger.info("Plan too large (%d tokens), splitting by sections", input_tokens)
        sections = re.split(r"\n(?=##\s)", plan_md)
        if len(sections) <= 1:
            # Can't split further — truncate and try
            truncated = plan_md[:int(self._context_window * 0.7 * 4)]
            try:
                result = self.call_llm_json(
                    render_prompt(PLAN_PARSER_USER, plan_md=truncated),
                    system_msg,
                )
                return self._build_testplan(result)
            except Exception as e:
                logger.warning("LLM plan parsing failed: %s", e)
                result = self._regex_parse(plan_md)
                return self._build_testplan(result)

        # Process sections in chunks
        all_results = []
        for i in range(0, len(sections), 3):
            chunk = "\n".join(sections[i:i + 3])
            chunk_prompt = (
                f"{PLAN_CHUNK_NOTICE.format(part=i // 3 + 1)}\n\n"
                f"{render_prompt(PLAN_PARSER_USER, plan_md=chunk)}"
            )
            try:
                result = self.call_llm_json(chunk_prompt, system_msg)
                all_results.append(result)
            except Exception as e:
                logger.warning("Chunk %d parsing failed: %s", i // 3 + 1, e)
                all_results.append(self._regex_parse(chunk))

        merged = self._merge_plan_results(all_results)
        return self._build_testplan(merged)

    def _merge_plan_results(self, results: list) -> dict:
        """Merge parsed plan results from multiple chunks."""
        merged: dict = {
            "api_definitions": [],
            "single_test_points": {},
            "biz_flow_scenarios": [],
        }
        seen_api = set()
        for r in results:
            for ad in r.get("api_definitions", []):
                key = (ad.get("test_id", ""), ad.get("url", ""))
                if key not in seen_api:
                    seen_api.add(key)
                    merged["api_definitions"].append(ad)
            for api_id, points in r.get("single_test_points", {}).items():
                if api_id not in merged["single_test_points"]:
                    merged["single_test_points"][api_id] = []
                seen_tps = {tp.get("test_id") for tp in merged["single_test_points"][api_id]}
                for tp in points:
                    if tp.get("test_id") not in seen_tps:
                        merged["single_test_points"][api_id].append(tp)
            for scenario in r.get("biz_flow_scenarios", []):
                merged["biz_flow_scenarios"].append(scenario)
        return merged

    def _build_testplan(self, result: dict) -> TestPlan:

        api_defs = []
        for ad in result.get("api_definitions", []):
            api_defs.append(InterfaceDef(
                test_id=ad.get("test_id", ""),
                api_name=ad.get("api_name", ""),
                app_name=ad.get("app_name", ""),
                method=ad.get("method", "GET"),
                url=ad.get("url", ""),
            ))

        test_points: Dict[str, List[PlanStep]] = {}
        for api_id, points in result.get("single_test_points", {}).items():
            steps = []
            for p in points:
                steps.append(PlanStep(
                    test_id=p.get("test_id", ""),
                    description=p.get("description", ""),
                    tag=p.get("tag", "P1"),
                    scenario_type=p.get("scenario_type", "positive"),
                ))
            test_points[api_id] = steps

        return TestPlan(
            api_definitions=api_defs,
            single_test_points=test_points,
            biz_flow_scenarios=result.get("biz_flow_scenarios", []),
        )

    def _regex_parse(self, plan_md: str) -> Dict[str, Any]:
        """Fallback regex-based parsing."""
        result: Dict[str, Any] = {
            "api_definitions": [],
            "single_test_points": {},
            "biz_flow_scenarios": [],
        }

        # Find API method+URL patterns
        api_pattern = re.findall(
            r'\|\s*(?:api_\w+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*(GET|POST|PUT|DELETE|PATCH)\s*\|\s*([^|]+)\s*\|',
            plan_md, re.IGNORECASE
        )
        for m in api_pattern:
            result["api_definitions"].append({
                "test_id": "",
                "api_name": m[0].strip(),
                "app_name": m[1].strip(),
                "method": m[2].strip().upper(),
                "url": m[3].strip(),
            })

        return result

    @staticmethod
    def _extract_section(text: str, start_pattern: str, end_pattern: str) -> str:
        """Extract content between two regex patterns."""
        start_match = re.search(start_pattern, text)
        if not start_match:
            return ""
        start_pos = start_match.end()
        end_match = re.search(end_pattern, text[start_pos:])
        if end_match:
            return text[start_pos:start_pos + end_match.start()].strip()
        return text[start_pos:].strip()

    @staticmethod
    def _extract_mermaid(text: str) -> Dict[str, str]:
        """Extract Mermaid diagrams from markdown."""
        diagrams: Dict[str, str] = {}
        pattern = re.compile(r'```mermaid\s*([\s\S]*?)\s*```')
        for i, match in enumerate(pattern.finditer(text)):
            name = f"flow_{i + 1}"
            content = match.group(1).strip()
            # Try to extract a title from the diagram
            title_match = re.search(r'title\s+(.+)', content)
            if title_match:
                name = title_match.group(1).strip()
            diagrams[name] = content
        return diagrams
