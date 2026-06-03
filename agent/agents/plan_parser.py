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

    def __init__(self, settings: Settings):
        super().__init__(
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            temperature=0.1,
            max_tokens=settings.llm_max_tokens,
            max_retries=settings.max_retries,
            max_steps=settings.max_steps,
            base_url=settings.llm_base_url,
        )

    def parse(self, plan_md: str) -> TestPlan:
        """Parse plan markdown into a structured TestPlan."""
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

        return plan

    def _llm_parse(self, plan_md: str) -> TestPlan:
        """Use LLM to extract structured test points from the plan."""
        system_msg = """你是一个专业的测试计划解析器。从 Markdown 测试计划中提取结构化信息。

请以 JSON 格式返回，格式如下：
```json
{
  "api_definitions": [
    {
      "test_id": "api_xxx",
      "api_name": "接口名",
      "app_name": "应用名",
      "method": "GET",
      "url": "/api/xxx"
    }
  ],
  "single_test_points": {
    "api_xxx": [
      {"test_id": "TP_001", "description": "测试点描述", "tag": "P0", "scenario_type": "positive"}
    ]
  },
  "biz_flow_scenarios": [
    {
      "name": "业务场景名",
      "description": "场景描述",
      "steps": ["Step01: 登录", "Step02: 查询"]
    }
  ]
}
```
"""

        prompt = f"请解析以下测试计划，提取结构化信息：\n\n{plan_md[:10000]}"

        try:
            result = self.call_llm_json(prompt, system_msg)
        except Exception as e:
            logger.warning("LLM plan parsing failed: %s, using regex fallback", e)
            result = self._regex_parse(plan_md)

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
