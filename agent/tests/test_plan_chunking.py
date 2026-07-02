"""分块计划生成测试 / Tests for chunked plan generation.

All LLM calls are mocked — NO real API calls.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from agents.base import BaseAgent
from agents.plan_generator import PlanGenerator
from config.settings import Settings
from graph.nodes import helpers as _h


# ---------------------------------------------------------------------------
# Shared helpers / 共享辅助函数
# ---------------------------------------------------------------------------

def _make_settings(**kwargs):
    s = Settings(llm_api_key="test")
    s.plan_single_batch_size = kwargs.get("plan_single_batch_size", 8)
    s.plan_biz_flow_batch_size = kwargs.get("plan_biz_flow_batch_size", 3)
    return s


def _make_agent(settings=None):
    BaseAgent._shared_client = MagicMock()
    if settings is None:
        settings = _make_settings()
    return PlanGenerator(settings)


def _sample_outline():
    return {
        "business_summary": "Test e-commerce system",
        "api_groups": [
            {
                "group_name": "User APIs",
                "api_ids": ["api_user_001"],
                "test_focus": "Authentication",
            },
        ],
        "biz_flows": [],
    }


def _sample_interfaces():
    return [
        {
            "test_id": "api_user_001",
            "api_name": "Login",
            "method": "POST",
            "url": "/login",
            "app_name": "user",
            "request_head": {},
            "request_body": {},
            "status_code": 200,
            "assert_dict": {},
            "remark": "",
        },
    ]


# ---------------------------------------------------------------------------
# TestPlanChunking
# ---------------------------------------------------------------------------

class TestPlanChunking:
    """Tests for PlanGenerator.generate_from_outline()."""

    def should_execute_phases_in_order(self):
        """Phase A → B → D 正确顺序执行 / Phases execute in correct order."""
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            agent = _make_agent()
            call_order = []

            def phase_a(prompt, system):
                call_order.append("A")
                return "## 1. Business Understanding\n\nTest\n\n## 4. Flowchart\n```mermaid\ngraph TD\n```"

            def phase_b(prompt, system):
                call_order.append("B")
                return "## 2.1 User APIs\n\nTest points"

            agent.call_llm = MagicMock(side_effect=[phase_a("", ""), phase_b("", "")])

            agent.generate_from_outline(
                outline=_sample_outline(),
                requirement_analysis={"flows": 1},
                interfaces=_sample_interfaces(),
            )

            assert call_order == ["A", "B"]

    def should_split_by_api_groups(self):
        """按 outline api_groups 拆分 chunk / Split by api_groups."""
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            agent = _make_agent()
            outline = {
                "business_summary": "Test",
                "api_groups": [
                    {"group_name": "Group A", "api_ids": ["api_a"], "test_focus": "Focus A"},
                    {"group_name": "Group B", "api_ids": ["api_b"], "test_focus": "Focus B"},
                ],
                "biz_flows": [],
            }
            interfaces = [
                {"test_id": "api_a", "api_name": "A", "method": "GET", "url": "/a", "app_name": "x", "request_head": {}, "request_body": {}, "status_code": 200, "assert_dict": {}, "remark": ""},
                {"test_id": "api_b", "api_name": "B", "method": "POST", "url": "/b", "app_name": "x", "request_head": {}, "request_body": {}, "status_code": 200, "assert_dict": {}, "remark": ""},
            ]

            call_count = [0]
            def side_effect(prompt, system):
                call_count[0] += 1
                if call_count[0] == 1:
                    return "## 1. Business Understanding\n\nGlobal context\n\n## 4. Mermaid\n```mermaid\ngraph TD\n```"
                return f"## Chunk {call_count[0]}"

            agent.call_llm = MagicMock(side_effect=side_effect)

            plan_md = agent.generate_from_outline(
                outline=outline,
                requirement_analysis={"flows": 1},
                interfaces=interfaces,
            )

            # Phase A(1) + Phase B(2 groups) = 3 calls
            assert call_count[0] == 3
            assert "Global context" in plan_md

    def should_assemble_in_correct_order(self):
        """拼接顺序正确：Global → API groups → Biz flows."""
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            agent = _make_agent()
            outline = {
                "business_summary": "Test",
                "api_groups": [
                    {"group_name": "First Group", "api_ids": ["api_1"], "test_focus": "First"},
                    {"group_name": "Second Group", "api_ids": ["api_2"], "test_focus": "Second"},
                ],
                "biz_flows": [
                    {"name": "My Flow", "description": "A flow", "involved_apis": ["api_1"]},
                ],
            }
            interfaces = [
                {"test_id": "api_1", "api_name": "API1", "method": "GET", "url": "/1", "app_name": "x", "request_head": {}, "request_body": {}, "status_code": 200, "assert_dict": {}, "remark": ""},
                {"test_id": "api_2", "api_name": "API2", "method": "POST", "url": "/2", "app_name": "x", "request_head": {}, "request_body": {}, "status_code": 200, "assert_dict": {}, "remark": ""},
            ]

            outputs = [
                "GLOBAL_CONTEXT",
                "FIRST_GROUP_SECTION",
                "SECOND_GROUP_SECTION",
                "BIZ_FLOW_SECTION",
            ]
            agent.call_llm = MagicMock(side_effect=outputs)

            plan_md = agent.generate_from_outline(
                outline=outline,
                requirement_analysis={"flows": 1},
                interfaces=interfaces,
            )

            # 验证拼接顺序 / Verify assembly order
            assert plan_md.index("GLOBAL_CONTEXT") < plan_md.index("FIRST_GROUP_SECTION")
            assert plan_md.index("FIRST_GROUP_SECTION") < plan_md.index("SECOND_GROUP_SECTION")

    def should_raise_error_when_outline_missing(self):
        """outline 缺失时 generate_plan_node 报错 / Error when outline is None."""
        from graph.nodes.generate_plan import generate_plan_node
        from graph.state import GraphState

        # 初始化 settings (generate_plan_node 内部需要 _h._settings)
        # Initialize settings (required internally by generate_plan_node)
        _h.configure(Settings(llm_api_key="test"), knowledge=None)

        state: GraphState = {
            "plan_outline": None,
            "requirement_analysis": {},
            "interfaces": [],
            "errors": [],
        }

        result = generate_plan_node(state)
        assert len(result.get("errors", [])) > 0
