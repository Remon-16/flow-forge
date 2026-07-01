"""Tests for skeleton generation batching logic.
骨架生成分批逻辑测试。

All LLM calls are mocked — NO real API calls.
"""

from unittest.mock import MagicMock, patch

import pytest

from agents.base import BaseAgent
from agents.skeleton_generator import (
    SingleSkeletonGenerator,
    BizSkeletonGenerator,
    _serialize_partial_single,
)
from config.settings import Settings


# ---------------------------------------------------------------------------
# Shared helpers / 共享辅助函数
# ---------------------------------------------------------------------------

def _make_settings(**kwargs):
    """创建测试用 Settings / Create a minimal Settings object for testing."""
    s = Settings(llm_api_key="test")
    s.skeleton_batch_size = kwargs.get("skeleton_batch_size", 30)
    s.validation_rules = kwargs.get("validation_rules", [
        {"check": "skeleton_count", "strategy": "fail"},
    ])
    return s


def _make_agent(cls=SingleSkeletonGenerator, settings=None):
    """实例化 agent 并防止真实 API 调用 / Instantiate agent with safe defaults."""
    BaseAgent._shared_client = MagicMock()
    if settings is None:
        settings = _make_settings()
    return cls(settings)


class _Point:
    """模拟 PlanStep / Mock PlanStep."""

    def __init__(self, tag, test_id, description, scenario_type):
        self.tag = tag
        self.test_id = test_id
        self.description = description
        self.scenario_type = scenario_type


def _mock_plan_single(api_points: dict):
    """创建带 single_test_points 的 mock plan。
    api_points: {"api_id": count, ...}
    """
    plan = MagicMock()
    plan.business_summary = "Test business summary"
    single = {}
    for api_id, count in api_points.items():
        single[api_id] = [
            _Point("P0", f"{api_id}_tp{i}", f"desc {i}", "positive")
            for i in range(count)
        ]
    plan.single_test_points = single
    return plan


def _mock_plan_biz(scenario_count: int):
    """创建带 biz_flow_scenarios 的 mock plan。"""
    plan = MagicMock()
    plan.business_summary = "Test biz summary"
    plan.biz_flow_scenarios = [
        {"name": f"flow_{i}", "description": f"desc_{i}"}
        for i in range(scenario_count)
    ]
    plan.mermaid_flows = {}
    return plan


def _valid_single_skeletons(count):
    """返回正确数量的 single_skeletons 响应。"""
    return {"single_skeletons": [{"test_id": f"sk_{i}"} for i in range(count)]}


def _valid_biz_skeletons(count):
    """返回正确数量的 biz_skeletons 响应。"""
    return {"biz_skeletons": [{"name": f"flow_{i}", "steps": []} for i in range(count)]}


# ---------------------------------------------------------------------------
# Single-batch path tests / 单批路径测试
# ---------------------------------------------------------------------------

class TestSingleBatchGeneration:
    """Tests for the single-batch (no split) code path."""

    def should_use_single_batch_when_points_leq_batch_size(self):
        """测试点 ≤ batch_size 时走单批路径 / Uses single batch when points ≤ batch_size."""
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            settings = _make_settings(skeleton_batch_size=30)
            agent = _make_agent(settings=settings)
            plan = _mock_plan_single({"api_a": 5, "api_b": 10})  # 15 total

            mock = MagicMock()
            mock.return_value = _valid_single_skeletons(15)
            agent.call_llm_json = mock

            result = agent.generate(plan, interfaces=[])
            assert len(result) == 15
            # 单次调用 / single call
            assert agent.call_llm_json.call_count == 1

    def should_return_empty_when_no_test_points(self):
        """无测试点时返回空列表 / Returns empty list when no test points."""
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            agent = _make_agent()
            plan = MagicMock()
            plan.single_test_points = {}
            plan.business_summary = ""

            result = agent.generate(plan, interfaces=[])
            assert result == []

    def should_retry_on_count_mismatch(self):
        """单批模式下数量不匹配时重试 / Retries on count mismatch in single batch."""
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            agent = _make_agent()
            plan = _mock_plan_single({"api_a": 3})
            mock = MagicMock()
            mock.side_effect = [
                {"single_skeletons": [{"test_id": "x"}]},  # wrong count
                _valid_single_skeletons(3),                 # correct
            ]
            agent.call_llm_json = mock

            result = agent.generate(plan, interfaces=[])
            assert len(result) == 3
            assert agent.call_llm_json.call_count == 2


# ---------------------------------------------------------------------------
# Multi-batch splitting tests / 多批拆分测试
# ---------------------------------------------------------------------------

class TestMultiBatchSplitting:
    """Tests for multi-batch splitting logic."""

    def should_split_into_multiple_batches_when_exceeding_size(self):
        """超过 batch_size 时拆分为多批 / Splits into batches when exceeding size."""
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            settings = _make_settings(skeleton_batch_size=10)
            agent = _make_agent(settings=settings)
            plan = _mock_plan_single({"api_a": 8, "api_b": 7})  # 15 total

            call_count = [0]

            def side_effect(prompt, system_msg):
                call_count[0] += 1
                if call_count[0] == 1:
                    return _valid_single_skeletons(10)  # batch 1
                else:
                    return _valid_single_skeletons(5)   # batch 2

            agent.call_llm_json = MagicMock(side_effect=side_effect)

            result = agent.generate(plan, interfaces=[])
            assert len(result) == 15
            assert agent.call_llm_json.call_count == 2

    def should_handle_api_larger_than_batch_size(self):
        """单个 API 超过 batch_size 时跨批处理 / Handles single API larger than batch_size."""
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            settings = _make_settings(skeleton_batch_size=10)
            agent = _make_agent(settings=settings)
            plan = _mock_plan_single({"api_large": 25})  # 一个 API 25 个点

            call_count = [0]

            def side_effect(prompt, system_msg):
                call_count[0] += 1
                if call_count[0] == 1:
                    return _valid_single_skeletons(10)
                elif call_count[0] == 2:
                    return _valid_single_skeletons(10)
                else:
                    return _valid_single_skeletons(5)

            agent.call_llm_json = MagicMock(side_effect=side_effect)

            result = agent.generate(plan, interfaces=[])
            assert len(result) == 25
            assert agent.call_llm_json.call_count == 3

    def should_preserve_total_count(self):
        """分批合并后总数等于原始测试点总数 / Preserves total count after batching."""
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            settings = _make_settings(skeleton_batch_size=5)
            agent = _make_agent(settings=settings)
            # 3 APIs, 12 points → 3 batches (5+5+2)
            plan = _mock_plan_single({"a": 3, "b": 5, "c": 4})

            call_count = [0]

            def side_effect(prompt, system_msg):
                call_count[0] += 1
                if call_count[0] == 1:
                    return _valid_single_skeletons(5)
                elif call_count[0] == 2:
                    return _valid_single_skeletons(5)
                else:
                    return _valid_single_skeletons(2)

            agent.call_llm_json = MagicMock(side_effect=side_effect)

            result = agent.generate(plan, interfaces=[])
            assert len(result) == 12

    def should_pass_all_interfaces_to_each_batch(self):
        """每批都传入全部接口定义（不过滤）/ Passes all interfaces to each batch."""
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            settings = _make_settings(skeleton_batch_size=5)
            agent = _make_agent(settings=settings)
            plan = _mock_plan_single({"api_a": 4, "api_b": 4})
            interfaces = [
                {"test_id": "api_a", "method": "GET", "url": "/a"},
                {"test_id": "api_b", "method": "POST", "url": "/b"},
            ]

            # 追踪 _build_prompt 调用来检查 prompt 内容
            # Track _build_prompt calls to check prompt content
            prompts = []
            real_build = agent._build_prompt

            def track_build(*args, **kwargs):
                prompt = real_build(*args, **kwargs)
                prompts.append(prompt)
                return prompt

            agent._build_prompt = track_build

            call_count = [0]

            def side_effect(prompt, system_msg):
                call_count[0] += 1
                if call_count[0] == 1:
                    return _valid_single_skeletons(5)
                else:
                    return _valid_single_skeletons(3)

            agent.call_llm_json = MagicMock(side_effect=side_effect)

            agent.generate(plan, interfaces=interfaces)
            # 每批 prompt 都包含两个接口定义 / each batch prompt includes both interfaces
            for p in prompts:
                assert '"test_id": "api_a"' in p
                assert '"test_id": "api_b"' in p

    def should_include_batch_notice_in_prompt(self):
        """分批 prompt 包含批次提示 / Batch prompt includes batch notice."""
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            settings = _make_settings(skeleton_batch_size=3)
            agent = _make_agent(settings=settings)
            plan = _mock_plan_single({"api_a": 5})

            prompts = []
            real_build = agent._build_prompt

            def track_build(*args, **kwargs):
                prompt = real_build(*args, **kwargs)
                prompts.append(prompt)
                return prompt

            agent._build_prompt = track_build

            call_count = [0]

            def side_effect(prompt, system_msg):
                call_count[0] += 1
                if call_count[0] == 1:
                    return _valid_single_skeletons(3)
                else:
                    return _valid_single_skeletons(2)

            agent.call_llm_json = MagicMock(side_effect=side_effect)

            agent.generate(plan, interfaces=[])
            # 两批都有批次提示 / both batches have batch notice
            assert "[Batch 1/2]" in prompts[0]
            assert "[Batch 2/2]" in prompts[1]


# ---------------------------------------------------------------------------
# Biz flow batching tests / 业务链路分批测试
# ---------------------------------------------------------------------------

class TestBizFlowBatching:
    """Tests for biz flow skeleton batching."""

    def should_not_split_when_scenarios_leq_batch_size(self):
        """场景数 ≤ batch_size 时不拆分 / No split when scenarios ≤ batch_size."""
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            settings = _make_settings(skeleton_batch_size=30)
            agent = _make_agent(BizSkeletonGenerator, settings=settings)
            plan = _mock_plan_biz(5)

            mock = MagicMock()
            mock.return_value = _valid_biz_skeletons(5)
            agent.call_llm_json = mock

            result = agent.generate(plan, interfaces=[])
            assert len(result) == 5
            assert agent.call_llm_json.call_count == 1

    def should_split_when_scenarios_exceed_batch_size(self):
        """场景数超过 batch_size 时拆分 / Splits when scenarios exceed batch_size."""
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            settings = _make_settings(skeleton_batch_size=2)
            agent = _make_agent(BizSkeletonGenerator, settings=settings)
            plan = _mock_plan_biz(5)

            call_count = [0]

            def side_effect(prompt, system_msg):
                call_count[0] += 1
                if call_count[0] == 1:
                    return _valid_biz_skeletons(2)
                elif call_count[0] == 2:
                    return _valid_biz_skeletons(2)
                else:
                    return _valid_biz_skeletons(1)

            agent.call_llm_json = MagicMock(side_effect=side_effect)

            result = agent.generate(plan, interfaces=[])
            assert len(result) == 5
            assert agent.call_llm_json.call_count == 3

    def should_return_empty_when_no_scenarios(self):
        """无场景时返回空列表 / Returns empty list when no scenarios."""
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            agent = _make_agent(BizSkeletonGenerator)
            plan = MagicMock()
            plan.biz_flow_scenarios = []
            plan.business_summary = ""

            result = agent.generate(plan, interfaces=[])
            assert result == []


# ---------------------------------------------------------------------------
# _serialize_partial_single tests / 部分序列化测试
# ---------------------------------------------------------------------------

class TestSerializePartialSingle:
    """Tests for _serialize_partial_single()."""

    def should_only_include_batch_apis(self):
        """只包含本批 API / Only includes batch APIs."""
        plan = MagicMock()
        plan.business_summary = "Summary"
        batch = {"api_a": [_Point("P0", "t1", "desc", "normal")]}

        result = _serialize_partial_single(batch, plan)
        assert "api_a" in result
        # 不在本批的 API 不出现 / API not in batch should not appear
        assert "api_b" not in result
        assert "Summary" in result
        assert "t1" in result

    def should_work_without_business_summary(self):
        """无 business_summary 时正常工作 / Works without business_summary."""
        plan = MagicMock()
        plan.business_summary = None
        batch = {"api_a": [_Point("P0", "t1", "desc", "normal")]}

        result = _serialize_partial_single(batch, plan)
        assert "api_a" in result
        assert "t1" in result

    def should_handle_empty_batch(self):
        """空批次正常工作 / Handles empty batch."""
        plan = MagicMock()
        plan.business_summary = "Summary"

        result = _serialize_partial_single({}, plan)
        assert "Summary" in result
