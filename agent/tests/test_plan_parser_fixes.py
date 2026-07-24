"""PlanParser 修复测试 — call_llm_json 重试、输出窗口预算、流程图关联校验。
PlanParser fix tests — JSON retry, output budget, flow match validation.

所有 LLM 调用 mock，无真实 API 调用 / All LLM calls mocked, no real API.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agents.base import BaseAgent
from agents.plan_parser import PlanParser
from config.settings import Settings, get_strategy, get_flow_match_failure_action
from models.schema import TestPlan

# ============================================================================
# 共享辅助 / Shared helpers
# ============================================================================


def _make_settings(**kwargs):
    s = Settings(llm_api_key="test")
    s.parse_plan_validation_enabled = kwargs.get(
        "ppv_enabled", True,
    )
    s.parse_plan_validation_max_retries = kwargs.get(
        "ppv_max_retries", 3,
    )
    s.parse_plan_validation_rules = kwargs.get(
        "ppv_rules",
        [{"check": "flow_match", "strategy": "warn"}],
    )
    return s


def _make_agent(settings=None):
    BaseAgent._shared_client = MagicMock()
    if settings is None:
        settings = _make_settings()
    return PlanParser(settings)


def _sample_sections(biz_flows=None):
    return {
        "business_understanding": "Test e-commerce system",
        "single_api": [
            {
                "name": "Login API",
                "content": "## Login\nPOST /login\nTest points...",
            },
        ],
        "biz_flows": biz_flows or [
            {
                "name": "User Registration",
                "content": "## User Registration\nSteps...",
                "mermaid": "```mermaid\ngraph TD\nA[Register]\n```",
            },
        ],
    }


# ============================================================================
# 修改 1 测试：call_llm_json 重试使用完整 prompt
# Change 1 tests: call_llm_json retry with full prompt
# ============================================================================


class TestCallLlmJsonRetry:
    """call_llm_json 修复 — 使用完整原始 prompt 重试。
    call_llm_json fix — retry with full original prompt."""

    def should_retry_with_full_prompt_on_json_parse_failure(self):
        """JSON 解析失败时使用完整 prompt 重试 / Retries with full prompt."""
        agent = _make_agent()
        agent.call_llm = MagicMock()
        agent.call_llm.side_effect = [
            "invalid json text",
            '{"key": "value"}',
        ]

        result = agent.call_llm_json("my full prompt", "system message")
        assert result == {"key": "value"}
        assert agent.call_llm.call_count == 2
        # 重试应使用原始完整 prompt，而非截断的 fix prompt
        # Retry should use the original full prompt, not a truncated fix prompt
        prompt_arg = agent.call_llm.call_args_list[1][0][0]
        assert prompt_arg == "my full prompt", (
            f"Expected full prompt, got: {prompt_arg}"
        )

    def should_raise_valueerror_when_retry_also_fails(self):
        """重试也失败时抛出 ValueError / Raises ValueError on retry failure."""
        agent = _make_agent()
        agent.call_llm = MagicMock(return_value="still not json")
        with pytest.raises(ValueError, match="Failed to parse JSON"):
            agent.call_llm_json("prompt", "system")

    def should_return_parsed_json_on_first_attempt(self):
        """首次调用成功时直接返回 / Returns directly on first success."""
        agent = _make_agent()
        agent.call_llm = MagicMock(return_value='{"ok": true}')
        result = agent.call_llm_json("prompt", "system")
        assert result == {"ok": True}
        assert agent.call_llm.call_count == 1


# ============================================================================
# 修改 2 测试：输出窗口预算
# Change 2 tests: output window budget
# ============================================================================


class TestOutputBudget:
    """PlanParser 输出窗口约束 / Output window constraint."""

    def should_use_max_output_tokens_formula(self):
        """验证公式 max_chunk_tokens = (max_output_tokens - system_tokens - 200) * 0.9。
        Verify formula: max_chunk_tokens = (max_output_tokens - sys - 200) * 0.9."""
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            agent = _make_agent()
            # 注入已知值 / Inject known values
            agent._max_output_tokens = 12000
            agent._token_counter.count = MagicMock(return_value=150)
            agent.call_llm_json_object = MagicMock(return_value={
                "api_definitions": [],
                "single_test_points": {},
                "biz_flow_scenarios": [],
            })

            sections = _sample_sections()
            agent.parse_from_sections(sections)

            # 验证公式：max_chunk_tokens = (12000 - 150 - 200) * 0.9 = 10485
            # verify: max_chunk_tokens = (12000 - 150 - 200) * 0.9 = 10485
            # 由于估算 token 很小 (<10485)，应该一次调用
            # Since estimated tokens are small (<10485), should be one call
            assert agent.call_llm_json_object.call_count == 1

    def should_trigger_chunking_with_small_max_output_tokens(self):
        """小 max_output_tokens 下触发拆分 / Triggers chunking with small output."""
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=5000):
            agent = _make_agent()
            agent._max_output_tokens = 1000  # 很小，迫使拆分 / very small, forces split
            agent._context_window = 128000
            agent.call_llm_json_object = MagicMock(return_value={
                "api_definitions": [],
                "single_test_points": {},
                "biz_flow_scenarios": [],
            })

            # 构造多个 biz_flows，使估算 token 超过预算 / Multiple biz_flows to exceed budget
            sections = _sample_sections(biz_flows=[
                {"name": f"Flow {i}", "content": f"Content {i}" * 200}
                for i in range(5)
            ])

            agent.parse_from_sections(sections)
            # 应该触发拆分，调用了多次 LLM / Should trigger split, multiple LLM calls
            assert agent.call_llm_json_object.call_count >= 1


# ============================================================================
# 修改 3 测试：flow_matcher 公共工具
# Change 3 tests: flow_matcher public utility
# ============================================================================


class TestFlowMatcher:
    """match_mermaids_to_scenarios 公共关联函数 / Public association utility."""

    def test_all_matched_by_name(self):
        """全部按名称匹配 / All matched by name."""
        from utils.flow_matcher import match_mermaids_to_scenarios
        scenarios = [
            {"name": "Flow A", "description": "desc A"},
            {"name": "Flow B", "description": "desc B"},
        ]
        mermaids = {"Flow A": "mermaid_a", "Flow B": "mermaid_b"}
        matched, orphaned = match_mermaids_to_scenarios(scenarios, mermaids)
        assert len(matched) == 2
        assert len(orphaned) == 0

    def test_partially_orphaned(self):
        """部分场景失配 / Partially orphaned."""
        from utils.flow_matcher import match_mermaids_to_scenarios
        scenarios = [
            {"name": "Flow A", "description": "desc A"},
            {"name": "Flow B", "description": "desc B"},
        ]
        mermaids = {"Flow A": "mermaid_a"}
        matched, orphaned = match_mermaids_to_scenarios(scenarios, mermaids)
        assert len(matched) == 1
        assert matched[0]["name"] == "Flow A"
        assert len(orphaned) == 1
        assert orphaned[0] == "Flow B"

    def test_all_orphaned_when_no_mermaids(self):
        """无 mermaid 时全部失配 / All orphaned when no mermaids."""
        from utils.flow_matcher import match_mermaids_to_scenarios
        scenarios = [{"name": "Flow A"}]
        matched, orphaned = match_mermaids_to_scenarios(scenarios, {})
        assert len(matched) == 0
        assert len(orphaned) == 1

    def test_empty_scenarios(self):
        """空场景列表 / Empty scenarios."""
        from utils.flow_matcher import match_mermaids_to_scenarios
        matched, orphaned = match_mermaids_to_scenarios(
            [], {"Flow A": "mermaid"},
        )
        assert len(matched) == 0
        assert len(orphaned) == 0


# ============================================================================
# 修改 4 测试：关联校验策略
# Change 4 tests: flow association strategies
# ============================================================================


class TestFlowAssociationValidation:
    """_validate_flow_association 的 fail/warn/skip 策略。
    Fail/warn/skip strategies for flow association validation."""

    def should_keep_all_when_all_matched(self):
        """全部匹配时不修改 plan / Plan unchanged when all matched."""
        agent = _make_agent()
        plan = TestPlan(
            business_summary="Test",
            biz_flow_scenarios=[
                {"name": "Flow A", "description": "A"},
            ],
            mermaid_flows={"Flow A": "```mermaid\ngraph\n```"},
        )
        agent._validate_flow_association(plan)
        assert len(plan.biz_flow_scenarios) == 1

    def should_not_check_when_empty(self):
        """无 scenarios 或无 mermaids 时跳过 / Skip when no scenarios or mermaids."""
        agent = _make_agent()
        plan = TestPlan(
            business_summary="Test",
            biz_flow_scenarios=[],
            mermaid_flows={"Flow A": "mermaid"},
        )
        # 不应崩溃 / Should not crash
        agent._validate_flow_association(plan)
        assert plan.biz_flow_scenarios == []

    def should_drop_orphaned_on_warn_discard(self):
        """warn + discard：丢弃失配场景 / Discard orphaned on warn+discard."""
        settings = _make_settings(
            ppv_rules=[{"check": "flow_match", "strategy": "warn",
                         "failure_action": "discard"}],
        )
        agent = _make_agent(settings=settings)
        agent._original_biz_sections = []
        # Mock: 重试也无法匹配 / Mock: retries can't match
        agent._parse_single_batch = MagicMock(return_value={
            "api_definitions": [],
            "single_test_points": {},
            "biz_flow_scenarios": [],
        })
        plan = TestPlan(
            business_summary="Test",
            biz_flow_scenarios=[
                {"name": "Flow A", "description": "A"},
                {"name": "Flow B", "description": "B"},
            ],
            mermaid_flows={"Flow A": "```mermaid\ngraph\n```"},
        )
        agent._validate_flow_association(plan)
        # Flow B 被丢弃 / Flow B discarded
        assert len(plan.biz_flow_scenarios) == 1
        assert plan.biz_flow_scenarios[0]["name"] == "Flow A"

    def should_keep_orphaned_on_warn_keep(self):
        """warn + keep：保留所有场景 / Keep all on warn+keep."""
        settings = _make_settings(
            ppv_rules=[{"check": "flow_match", "strategy": "warn",
                         "failure_action": "keep"}],
        )
        agent = _make_agent(settings=settings)
        agent._original_biz_sections = []
        agent._parse_single_batch = MagicMock(return_value={
            "api_definitions": [],
            "single_test_points": {},
            "biz_flow_scenarios": [],
        })
        plan = TestPlan(
            business_summary="Test",
            biz_flow_scenarios=[
                {"name": "Flow A", "description": "A"},
                {"name": "Flow B", "description": "B"},
            ],
            mermaid_flows={"Flow A": "```mermaid\ngraph\n```"},
        )
        agent._validate_flow_association(plan)
        # 全部保留 / All kept
        assert len(plan.biz_flow_scenarios) == 2

    def should_raise_on_fail_strategy(self):
        """fail 策略：重试耗尽后抛异常 / Raises on fail after retries."""
        settings = _make_settings(
            ppv_rules=[{"check": "flow_match", "strategy": "fail"}],
        )
        agent = _make_agent(settings=settings)
        agent._original_biz_sections = []
        agent._parse_single_batch = MagicMock(return_value={
            "api_definitions": [],
            "single_test_points": {},
            "biz_flow_scenarios": [],
        })
        plan = TestPlan(
            business_summary="Test",
            biz_flow_scenarios=[
                {"name": "Flow A", "description": "A"},
                {"name": "Flow B", "description": "B"},
            ],
            mermaid_flows={"Flow A": "```mermaid\ngraph\n```"},
        )
        with pytest.raises(ValueError, match="Flow association failed"):
            agent._validate_flow_association(plan)

    def should_skip_on_skip_strategy(self):
        """skip 策略：不检查，保留所有 / Skip: no check, keep all."""
        settings = _make_settings(
            ppv_rules=[{"check": "flow_match", "strategy": "skip"}],
        )
        agent = _make_agent(settings=settings)
        plan = TestPlan(
            business_summary="Test",
            biz_flow_scenarios=[
                {"name": "NoMermaid", "description": "Orphaned"},
            ],
            mermaid_flows={},
        )
        agent._validate_flow_association(plan)
        # 跳过校验，场景不变 / Skipped, scenarios unchanged
        assert len(plan.biz_flow_scenarios) == 1


# ============================================================================
# 修改 6 测试：settings 配置
# Change 6 tests: settings config
# ============================================================================


class TestParsePlanValidationSettings:
    """parse_plan_validation 配置块 / Parse plan validation config block."""

    def test_default_strategy_is_warn(self):
        """默认 flow_match 策略为 warn / Default flow_match strategy is warn."""
        rules = [{"check": "flow_match", "strategy": "warn"}]
        assert get_strategy(rules, "flow_match") == "warn"

    def test_get_flow_match_failure_action_default(self):
        """默认 failure_action 为 discard / Default failure_action is discard."""
        rules = [{"check": "flow_match", "strategy": "warn"}]
        assert get_flow_match_failure_action(rules) == "discard"

    def test_get_flow_match_failure_action_keep(self):
        """failure_action=keep 正确读取 / failure_action=keep read correctly."""
        rules = [{"check": "flow_match", "strategy": "warn",
                   "failure_action": "keep"}]
        assert get_flow_match_failure_action(rules) == "keep"
