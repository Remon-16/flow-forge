"""轮廓生成测试 / Tests for plan outline generation.

All LLM calls are mocked — NO real API calls.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from agents.base import BaseAgent
from agents.plan_generator import PlanGenerator, _normalize_chunk_ids, _name_to_chunk_id
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


# ---------------------------------------------------------------------------
# Chunk ID Normalization / 分块 ID 规范化
# ---------------------------------------------------------------------------

class TestNameToChunkId:
    """Tests for _name_to_chunk_id — name → safe ASCII chunk_id conversion."""

    def should_convert_english_name(self):
        result = _name_to_chunk_id("User Authentication", prefix="api_")
        assert result == "api_user_authentication"

    def should_handle_chinese_name_with_prefix(self):
        # 纯中文无 ASCII 部分时用前缀 + 索引式兜底
        # Pure Chinese with no ASCII → falls back to prefix
        result = _name_to_chunk_id("认证与账户", prefix="api_")
        # 应至少以 api_ 开头
        assert result.startswith("api_")

    def should_keep_existing_prefix(self):
        result = _name_to_chunk_id("api_my_service", prefix="api_")
        assert result == "api_my_service"

    def should_collapse_multiple_underscores(self):
        result = _name_to_chunk_id("User  &  Auth !! Service", prefix="biz_")
        assert "__" not in result
        assert result.startswith("biz_")


class TestNormalizeChunkIds:
    """Tests for _normalize_chunk_ids — outline post-processing."""

    def should_preserve_provided_chunk_ids(self):
        outline = {
            "business_summary": "test",
            "api_groups": [
                {"chunk_id": "api_auth", "group_name": "Auth", "api_ids": ["api_001"]},
            ],
            "biz_flows": [
                {"chunk_id": "biz_register", "name": "Register", "involved_apis": ["api_001"]},
            ],
        }
        result = _normalize_chunk_ids(outline)
        assert result["api_groups"][0]["chunk_id"] == "api_auth"
        assert result["biz_flows"][0]["chunk_id"] == "biz_register"

    def should_generate_missing_chunk_ids(self):
        outline = {
            "api_groups": [
                {"group_name": "User APIs", "api_ids": ["api_001"]},
            ],
            "biz_flows": [
                {"name": "User Purchase", "involved_apis": ["api_001"]},
            ],
        }
        result = _normalize_chunk_ids(outline)
        assert result["api_groups"][0]["chunk_id"].startswith("api_")
        assert result["biz_flows"][0]["chunk_id"].startswith("biz_")

    def should_deduplicate_colliding_ids(self):
        outline = {
            "api_groups": [
                {"chunk_id": "api_same", "group_name": "A", "api_ids": ["api_001"]},
                {"chunk_id": "api_same", "group_name": "B", "api_ids": ["api_002"]},
            ],
            "biz_flows": [],
        }
        result = _normalize_chunk_ids(outline)
        ids = [g["chunk_id"] for g in result["api_groups"]]
        assert len(ids) == len(set(ids)), f"Duplicate IDs found: {ids}"
        assert ids[0] == "api_same"
        assert ids[1] != "api_same"

    def should_ensure_unique_across_api_and_biz(self):
        # 同一个名称同时出现在 api 和 biz / Same name in both api and biz
        outline = {
            "api_groups": [
                {"chunk_id": "auth", "group_name": "Auth", "api_ids": ["api_001"]},
            ],
            "biz_flows": [
                {"chunk_id": "auth", "name": "Auth Flow", "involved_apis": ["api_001"]},
            ],
        }
        result = _normalize_chunk_ids(outline)
        api_id = result["api_groups"][0]["chunk_id"]
        biz_id = result["biz_flows"][0]["chunk_id"]
        assert api_id != biz_id, f"Cross-type collision: {api_id}"
        assert api_id.startswith("api_") or biz_id.startswith("biz_")

    def should_handle_empty_outline(self):
        outline = {"api_groups": [], "biz_flows": []}
        result = _normalize_chunk_ids(outline)
        assert result["api_groups"] == []
        assert result["biz_flows"] == []
