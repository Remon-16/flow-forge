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


def _normalize_interfaces(items: List[Any]) -> List[Dict[str, Any]]:
    """Convert a mixed list of InterfaceDef/dicts to a unified list of dicts."""
    result = []
    for item in items:
        if isinstance(item, dict):
            result.append({
                "test_id": item.get("test_id", ""),
                "api_name": item.get("api_name", item.get("name", "")),
                "app_name": item.get("app_name", item.get("app", "")),
                "method": item.get("method", "GET"),
                "url": item.get("url", ""),
                "request_head": item.get("request_head", item.get("headers", {})),
                "request_body": item.get("request_body", item.get("body", {})),
                "status_code": item.get("status_code", 200),
                "assert_dict": item.get("assert_dict", {}),
                "remark": item.get("remark", item.get("note", "")),
            })
        elif hasattr(item, "test_id"):
            result.append({
                "test_id": item.test_id,
                "api_name": item.api_name,
                "app_name": item.app_name,
                "method": item.method,
                "url": item.url,
                "request_head": item.request_head,
                "request_body": item.request_body,
                "status_code": item.status_code,
                "assert_dict": item.assert_dict,
                "remark": item.remark,
            })
        else:
            logger.warning("Skipping unrecognized interface item: %s", type(item))
    return result


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
            base_url=settings.llm_base_url,
        )
        self._knowledge = knowledge

    def generate(
        self,
        plan: TestPlan,
        interfaces: List[Any],
        user_guidance: str = "",
    ) -> Dict[str, Any]:
        """Generate single and biz test cases.

        Args:
            plan: Structured TestPlan from PlanParser.
            interfaces: List of InterfaceDef objects OR plain dicts from state.
            user_guidance: Optional user guidance from --prompt CLI flag.

        Returns dict with keys: 'single_cases', 'biz_flows'
        """
        # Serialize plan and interfaces for LLM
        plan_str = self._serialize_plan(plan)
        iface_dicts = _normalize_interfaces(interfaces)

        prompt = render_prompt(
            CASE_GENERATION_USER,
            test_plan=plan_str,
            interface_defs=json.dumps(iface_dicts, ensure_ascii=False, indent=2),
            user_guidance=user_guidance,
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

    def generate_batch(
        self,
        interfaces: List[Any],
        test_points: List[Dict],
        batch_type: str,
        user_guidance: str = "",
        previous_errors: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """Generate a batch of test cases for specific interfaces.

        Args:
            interfaces: Interface definitions relevant to this batch.
            test_points: Test points to cover in this batch.
            batch_type: "single" or "biz".
            user_guidance: Optional user guidance.
            previous_errors: Previous validation errors for retry context.

        Returns dict with 'single_cases' or 'biz_flows' key.
        """
        iface_dicts = _normalize_interfaces(interfaces)

        tp_summary = json.dumps(
            [{
                "test_id": tp.get("test_id", ""),
                "description": tp.get("description", ""),
                "tag": tp.get("tag", "P1"),
                "scenario_type": tp.get("scenario_type", "positive"),
            } for tp in test_points],
            ensure_ascii=False, indent=2,
        )

        error_context = ""
        if previous_errors:
            error_context = (
                "\n\n## 上次生成校验失败，请修正以下问题\n"
                + json.dumps(previous_errors, ensure_ascii=False, indent=2)
                + "\n请确保 JSON 格式正确，所有必填字段完整。"
            )

        if batch_type == "single":
            system = CASE_GENERATION_SYSTEM
            prompt = (
                f"## 本批接口定义\n```json\n{json.dumps(iface_dicts, ensure_ascii=False, indent=2)}\n```\n\n"
                f"## 本批测试点\n```json\n{tp_summary}\n```\n\n"
                f"## 用户指导\n{user_guidance or '(无)'}\n"
                f"{error_context}\n\n"
                f"请生成以上接口的单接口测试用例，只生成一个 JSON 对象，包含 single_cases 字段。"
            )

            result = self.call_llm_json(prompt, system)
            single_cases = self._parse_single_cases(result.get("single_cases", []))
            return {"single_cases": single_cases}
        else:
            scenarios = []
            for tp in test_points:
                scenarios.append({
                    "name": tp.get("name", tp.get("test_id", "")),
                    "description": tp.get("description", ""),
                })

            system = CASE_GENERATION_SYSTEM
            prompt = (
                f"## 本批接口定义\n```json\n{json.dumps(iface_dicts, ensure_ascii=False, indent=2)}\n```\n\n"
                f"## 本批业务链路场景\n```json\n{json.dumps(scenarios, ensure_ascii=False, indent=2)}\n```\n\n"
                f"## 用户指导\n{user_guidance or '(无)'}\n"
                f"{error_context}\n\n"
                f"请生成以上业务链路的测试用例，每个链路包含多个步骤。"
                f"只生成一个 JSON 对象，包含 biz_flows 字段。"
            )

            result = self.call_llm_json(prompt, system)
            biz_flows = self._parse_biz_flows(result.get("biz_flows", []))
            return {"biz_flows": biz_flows}

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
