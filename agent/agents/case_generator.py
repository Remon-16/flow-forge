"""CaseGenerator: fill concrete params, generate single + biz test cases."""

import json
import logging
from typing import Any, Dict, List, Optional

from .base import BaseAgent
from config.settings import Settings
from knowledge.search import KnowledgeSearch
from models.schema import (
    BizFlow,
    BizStep,
    InterfaceDef,
    PlanStep,
    SingleTestCase,
    TestPlan,
)
from prompts.case_generation import CASE_GENERATION_SYSTEM, CASE_GENERATION_USER
from prompts.render import render_prompt

logger = logging.getLogger(__name__)


class CaseGenerator(BaseAgent):
    """Generate concrete test cases from a confirmed test plan."""

    def __init__(self, settings: Settings, knowledge: Optional[KnowledgeSearch] = None):
        super().__init__(
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            max_retries=settings.max_retries,
            max_steps=settings.max_steps,
        )
        self._knowledge = knowledge

    def generate(
        self,
        plan: TestPlan,
        interfaces: List[InterfaceDef],
    ) -> Dict[str, Any]:
        """Generate single and biz test cases.

        Returns dict with keys: 'single_cases', 'biz_flows'
        """
        # Build interface lookup
        iface_map: Dict[str, InterfaceDef] = {}
        for iface in interfaces:
            iface_map[iface.test_id] = iface

        # Serialize plan and interfaces for LLM
        plan_str = self._serialize_plan(plan)
        iface_dicts = []
        for iface in interfaces:
            iface_dicts.append({
                "test_id": iface.test_id,
                "api_name": iface.api_name,
                "app_name": iface.app_name,
                "method": iface.method,
                "url": iface.url,
                "request_head": iface.request_head,
                "request_body": iface.request_body,
                "status_code": iface.status_code,
                "assert_dict": iface.assert_dict,
                "remark": iface.remark,
            })

        prompt = render_prompt(
            CASE_GENERATION_USER,
            test_plan=plan_str,
            interface_defs=json.dumps(iface_dicts, ensure_ascii=False, indent=2),
        )

        # Conditionally append knowledge context
        if self._knowledge is not None:
            docs = self._knowledge.search("test case generation concrete values", n_results=3)
            if docs:
                knowledge_context = "\n---\n".join(docs)
                prompt += f"\n\n## 知识库参考\n{knowledge_context}"

        logger.info("Generating test cases from plan...")
        result = self.call_llm_json(prompt, CASE_GENERATION_SYSTEM)

        single_cases = self._parse_single_cases(result.get("single_cases", []))
        biz_flows = self._parse_biz_flows(result.get("biz_flows", []))

        logger.info(
            "Generated %d single cases, %d biz flows",
            len(single_cases), len(biz_flows),
        )
        return {"single_cases": single_cases, "biz_flows": biz_flows}

    def _parse_single_cases(self, raw_cases: List[Dict]) -> List[SingleTestCase]:
        cases = []
        for c in raw_cases:
            try:
                cases.append(SingleTestCase(
                    test_id=str(c.get("test_id", "")),
                    relevance_id=str(c.get("relevance_id", "")),
                    tag=str(c.get("tag", "P1")),
                    api_name=str(c.get("api_name", "")),
                    app_name=str(c.get("app_name", "")),
                    method=str(c.get("method", "GET")).upper(),
                    url=str(c.get("url", "")),
                    request_head=dict(c.get("request_head") or {}),
                    request_body=dict(c.get("request_body") or {}),
                    status_code=int(c.get("status_code", 200)),
                    assert_dict=dict(c.get("assert_dict") or {}),
                    remark=str(c.get("remark", "")),
                ))
            except Exception as e:
                logger.warning("Failed to parse single case: %s", e)
        return cases

    def _parse_biz_flows(self, raw_flows: List[Dict]) -> List[BizFlow]:
        flows = []
        for f in raw_flows:
            try:
                steps = []
                for s in f.get("steps", []):
                    steps.append(BizStep(
                        step_id=str(s.get("step_id", "")),
                        relevance_id=str(s.get("relevance_id", "")),
                        trans=str(s.get("trans", "")),
                        api_name=str(s.get("api_name", "")),
                        app_name=str(s.get("app_name", "")),
                        method=str(s.get("method", "GET")).upper(),
                        url=str(s.get("url", "")),
                        request_head=dict(s.get("request_head") or {}),
                        request_body=dict(s.get("request_body") or {}),
                        status_code=int(s.get("status_code", 200)),
                        assert_dict=dict(s.get("assert_dict") or {}),
                        tag=str(s.get("tag", "P1")),
                        remark=str(s.get("remark", "")),
                    ))
                flows.append(BizFlow(
                    sheet_name=str(f.get("sheet_name", "BizFlow")),
                    steps=steps,
                ))
            except Exception as e:
                logger.warning("Failed to parse biz flow: %s", e)
        return flows

    @staticmethod
    def _serialize_plan(plan: TestPlan) -> str:
        """Serialize TestPlan to a readable string for the LLM prompt."""
        parts = []

        if plan.business_summary:
            parts.append(f"## 业务理解\n{plan.business_summary}")

        if plan.api_definitions:
            parts.append("\n## 接口定义")
            for ad in plan.api_definitions:
                parts.append(
                    f"- {ad.test_id}: {ad.method} {ad.url} ({ad.api_name})"
                )

        if plan.single_test_points:
            parts.append("\n## 单接口测试点")
            for api_id, points in plan.single_test_points.items():
                parts.append(f"\n### {api_id}")
                for p in points:
                    parts.append(
                        f"- [{p.tag}] {p.test_id}: {p.description} ({p.scenario_type})"
                    )

        if plan.mermaid_flows:
            parts.append("\n## 业务流程图")
            for name, diagram in plan.mermaid_flows.items():
                parts.append(f"\n### {name}\n```mermaid\n{diagram}\n```")

        if plan.biz_flow_scenarios:
            parts.append("\n## 业务链路场景")
            for scenario in plan.biz_flow_scenarios:
                parts.append(
                    f"- {scenario.get('name', '')}: {scenario.get('description', '')}"
                )

        return "\n".join(parts)
