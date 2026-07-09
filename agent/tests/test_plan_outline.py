"""轮廓生成测试 / Tests for plan outline generation.

All LLM calls are mocked — NO real API calls.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from agents.base import BaseAgent
from agents.plan_generator import PlanGenerator
from config.settings import Settings


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


def _valid_outline():
    return {
        "business_summary": "Test business summary",
        "api_groups": [
            {
                "group_name": "User APIs",
                "api_ids": ["api_user_001", "api_user_002"],
                "test_focus": "Authentication and authorization",
            },
            {
                "group_name": "Product APIs",
                "api_ids": ["api_product_001"],
                "test_focus": "CRUD operations",
            },
        ],
        "biz_flows": [
            {
                "name": "User Purchase Flow",
                "description": "User browses products and purchases",
                "involved_apis": ["api_product_001", "api_user_001"],
            }
        ],
    }


# ---------------------------------------------------------------------------
# TestPlanOutlineGeneration
# ---------------------------------------------------------------------------

class TestPlanOutlineGeneration:
    """Tests for PlanGenerator.generate_outline()."""

    def should_generate_valid_outline_json(self):
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            agent = _make_agent()
            agent.call_llm_json = MagicMock(return_value=_valid_outline())

            outline = agent.generate_outline(
                requirement_analysis={"flows": 2, "roles": ["user"]},
                interface_names=[
                    {"test_id": "api_user_001", "api_name": "Login", "method": "POST", "url": "/login"},
                ],
            )

            assert "business_summary" in outline
            assert "api_groups" in outline
            assert "biz_flows" in outline
            assert len(outline["api_groups"]) == 2
            assert len(outline["biz_flows"]) == 1

    def should_group_interfaces_by_business_domain(self):
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            agent = _make_agent()
            agent.call_llm_json = MagicMock(return_value=_valid_outline())

            outline = agent.generate_outline(
                requirement_analysis={"flows": 1},
                interface_names=[
                    {"test_id": "api_user_001", "api_name": "Login", "method": "POST", "url": "/login"},
                    {"test_id": "api_user_002", "api_name": "Register", "method": "POST", "url": "/register"},
                    {"test_id": "api_product_001", "api_name": "GetProduct", "method": "GET", "url": "/product"},
                ],
            )

            # 验证每个 group 有 group_name 和 api_ids / Verify each group has required fields
            for group in outline["api_groups"]:
                assert "group_name" in group
                assert "api_ids" in group
                assert len(group["api_ids"]) > 0

    def should_handle_empty_interfaces(self):
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            agent = _make_agent()
            agent.call_llm_json = MagicMock(return_value={
                "business_summary": "No APIs",
                "api_groups": [],
                "biz_flows": [],
            })

            outline = agent.generate_outline(
                requirement_analysis={"flows": 0},
                interface_names=[],
            )

            assert outline["api_groups"] == []
            assert outline["biz_flows"] == []

    def should_raise_on_context_window_exceeded(self):
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=200000):
            agent = _make_agent()
            with pytest.raises(ValueError):
                agent.generate_outline(
                    requirement_analysis={"data": "x" * 10000},
                    interface_names=[{"test_id": "api_001", "api_name": "Test", "method": "GET", "url": "/test"}],
                )
