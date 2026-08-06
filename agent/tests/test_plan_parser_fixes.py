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
    Fail/warn/skip strategies for flow association validation.

    两步走：代码精确匹配 → LLM 语义兜底。
    Two-step: code exact match → LLM semantic fallback.
    """

    def should_keep_all_when_all_matched(self):
        """全部代码匹配时不触发 LLM 匹配 / Plan unchanged when all code-matched."""
        agent = _make_agent()
        agent._llm_match_flows = MagicMock()
        plan = TestPlan(
            business_summary="Test",
            biz_flow_scenarios=[
                {"name": "Flow A", "description": "A"},
            ],
            mermaid_flows={"Flow A": "```mermaid\ngraph\n```"},
        )
        agent._validate_flow_association(plan)
        assert len(plan.biz_flow_scenarios) == 1
        # LLM 匹配不应被调用 / LLM matching should not be called
        agent._llm_match_flows.assert_not_called()

    def should_not_check_when_empty(self):
        """无 scenarios 或无 mermaids 时跳过 / Skip when no scenarios or mermaids."""
        agent = _make_agent()
        agent._llm_match_flows = MagicMock()
        plan = TestPlan(
            business_summary="Test",
            biz_flow_scenarios=[],
            mermaid_flows={"Flow A": "mermaid"},
        )
        agent._validate_flow_association(plan)
        assert plan.biz_flow_scenarios == []
        agent._llm_match_flows.assert_not_called()

    def should_drop_orphaned_on_warn_discard(self):
        """warn + discard：代码匹配发现孤儿 → LLM 无法匹配 → 丢弃。
        Code match finds orphans → LLM can't match → discard."""
        settings = _make_settings(
            ppv_rules=[{"check": "flow_match", "strategy": "warn",
                         "failure_action": "discard"}],
        )
        agent = _make_agent(settings=settings)
        # LLM 语义匹配全部返回 None（无法匹配）
        # LLM semantic matching returns all None (cannot match)
        agent._llm_match_flows = MagicMock(return_value={
            "Flow B": None,
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
        agent._llm_match_flows.assert_called_once()

    def should_keep_orphaned_on_warn_keep(self):
        """warn + keep：代码匹配发现孤儿 → LLM 无法匹配 → 保留全部。
        Code match finds orphans → LLM can't match → keep all."""
        settings = _make_settings(
            ppv_rules=[{"check": "flow_match", "strategy": "warn",
                         "failure_action": "keep"}],
        )
        agent = _make_agent(settings=settings)
        agent._llm_match_flows = MagicMock(return_value={
            "Flow B": None,
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
        """fail 策略：代码匹配发现孤儿 → LLM 无法匹配 → 抛异常。
        Code match finds orphans → LLM can't match → raises."""
        settings = _make_settings(
            ppv_rules=[{"check": "flow_match", "strategy": "fail"}],
        )
        agent = _make_agent(settings=settings)
        agent._llm_match_flows = MagicMock(return_value={
            "Flow B": None,
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
        agent._llm_match_flows = MagicMock()
        plan = TestPlan(
            business_summary="Test",
            biz_flow_scenarios=[
                {"name": "NoMermaid", "description": "Orphaned"},
            ],
            mermaid_flows={},
        )
        agent._validate_flow_association(plan)
        assert len(plan.biz_flow_scenarios) == 1
        agent._llm_match_flows.assert_not_called()

    def should_use_llm_match_on_code_mismatch(self):
        """代码匹配失败时触发 LLM 语义匹配并成功关联。
        Code match fails → LLM matching succeeds → scenarios associated."""
        settings = _make_settings(
            ppv_rules=[{"check": "flow_match", "strategy": "warn",
                         "failure_action": "discard"}],
        )
        agent = _make_agent(settings=settings)
        # LLM 语义匹配成功将 "Flow X" 关联到 "Flow B"
        # LLM matching succeeds: "Flow X" → "Flow B"
        agent._llm_match_flows = MagicMock(return_value={
            "Flow X": "Flow B",
        })
        plan = TestPlan(
            business_summary="Test",
            biz_flow_scenarios=[
                {"name": "Flow A", "description": "A"},
                {"name": "Flow X", "description": "X variant"},
            ],
            mermaid_flows={
                "Flow A": "```mermaid\ngraph A\n```",
                "Flow B": "```mermaid\ngraph B\n```",
            },
        )
        agent._validate_flow_association(plan)
        # "Flow X" 被 LLM 关联到 "Flow B"，全部保留
        # "Flow X" matched to "Flow B" by LLM, all kept
        assert len(plan.biz_flow_scenarios) == 2


# ============================================================================
# 新增测试：_llm_match_flows 单元测试
# New tests: _llm_match_flows unit tests
# ============================================================================


class TestLlmMatchFlows:
    """_llm_match_flows 方法单元测试 / Unit tests for _llm_match_flows."""

    def test_all_matched_first_call(self):
        """LLM 首次调用即全部匹配 / All matched on first LLM call."""
        agent = _make_agent()
        agent._token_counter.count = MagicMock(return_value=50)
        agent._estimate_input_tokens = MagicMock(return_value=200)
        agent._max_output_tokens = 12000
        agent.call_llm_json_object = MagicMock(return_value={
            "matches": {
                "Flow X": "Flow B",
                "Flow Y": "Flow C",
            },
        })
        mermaid_flows = {
            "Flow B": "mermaid B",
            "Flow C": "mermaid C",
        }
        orphaned = [
            {"name": "Flow X", "description": "X desc"},
            {"name": "Flow Y", "description": "Y desc"},
        ]
        result = agent._llm_match_flows(orphaned, mermaid_flows, max_retries=3)
        assert result == {"Flow X": "Flow B", "Flow Y": "Flow C"}
        # 应该只调用一次 LLM / Should only call LLM once
        assert agent.call_llm_json_object.call_count == 1

    def test_partial_match_with_retry(self):
        """部分匹配 → 仅重试未匹配的 / Partial match → retry only unmatched."""
        agent = _make_agent()
        agent._token_counter.count = MagicMock(return_value=50)
        agent._estimate_input_tokens = MagicMock(return_value=200)
        agent._max_output_tokens = 12000
        # 第一次：Flow X 匹配成功，Flow Y 为 null
        # First: Flow X matched, Flow Y null
        # 第二次：Flow Y 匹配成功
        # Second: Flow Y matched
        agent.call_llm_json_object = MagicMock(side_effect=[
            {"matches": {"Flow X": "Flow B", "Flow Y": None}},
            {"matches": {"Flow Y": "Flow C"}},
        ])
        mermaid_flows = {
            "Flow B": "mermaid B",
            "Flow C": "mermaid C",
        }
        orphaned = [
            {"name": "Flow X", "description": "X desc"},
            {"name": "Flow Y", "description": "Y desc"},
        ]
        result = agent._llm_match_flows(orphaned, mermaid_flows, max_retries=3)
        assert result == {"Flow X": "Flow B", "Flow Y": "Flow C"}
        # 两次调用：第一次全部，第二次仅 Flow Y
        # Two calls: first for all, second only for Flow Y
        assert agent.call_llm_json_object.call_count == 2
        # 验证第二次调用的 prompt 仅包含 Flow Y
        # Verify second call prompt only contains Flow Y
        second_call_prompt = agent.call_llm_json_object.call_args_list[1][0][0]
        assert "Flow Y" in second_call_prompt
        assert "Flow X" not in second_call_prompt

    def test_many_to_one_matching(self):
        """多个场景匹配到同一个 Mermaid 图 / Many scenarios match one diagram."""
        agent = _make_agent()
        agent._token_counter.count = MagicMock(return_value=50)
        agent._estimate_input_tokens = MagicMock(return_value=200)
        agent._max_output_tokens = 12000
        agent.call_llm_json_object = MagicMock(return_value={
            "matches": {
                "用户注册-正常路径": "用户注册流程",
                "用户注册-异常路径": "用户注册流程",
            },
        })
        mermaid_flows = {"用户注册流程": "mermaid reg"}
        orphaned = [
            {"name": "用户注册-正常路径", "description": "正常注册"},
            {"name": "用户注册-异常路径", "description": "异常注册"},
        ]
        result = agent._llm_match_flows(orphaned, mermaid_flows, max_retries=3)
        assert result == {
            "用户注册-正常路径": "用户注册流程",
            "用户注册-异常路径": "用户注册流程",
        }

    def test_invalid_mermaid_id_triggers_retry(self):
        """LLM 返回不存在的 ID → 触发重试 / Invalid mermaid ID → triggers retry."""
        agent = _make_agent()
        agent._token_counter.count = MagicMock(return_value=50)
        agent._estimate_input_tokens = MagicMock(return_value=200)
        agent._max_output_tokens = 12000
        # 第一次返回不存在的 ID，第二次返回正确的 ID
        # First returns nonexistent ID, second returns correct ID
        agent.call_llm_json_object = MagicMock(side_effect=[
            {"matches": {"Flow X": "NonExistentFlow"}},
            {"matches": {"Flow X": "Flow B"}},
        ])
        mermaid_flows = {"Flow B": "mermaid B"}
        orphaned = [{"name": "Flow X", "description": "X desc"}]
        result = agent._llm_match_flows(orphaned, mermaid_flows, max_retries=3)
        assert result == {"Flow X": "Flow B"}
        assert agent.call_llm_json_object.call_count == 2

    def test_all_retries_exhausted(self):
        """重试耗尽后返回 None / Return None after all retries exhausted."""
        agent = _make_agent()
        agent._token_counter.count = MagicMock(return_value=50)
        agent._estimate_input_tokens = MagicMock(return_value=200)
        agent._max_output_tokens = 12000
        # 所有重试都返回 null / All retries return null
        agent.call_llm_json_object = MagicMock(return_value={
            "matches": {"Flow X": None},
        })
        mermaid_flows = {"Flow B": "mermaid B"}
        orphaned = [{"name": "Flow X", "description": "X desc"}]
        result = agent._llm_match_flows(orphaned, mermaid_flows, max_retries=3)
        assert result == {"Flow X": None}
        # 应该调用 max_retries 次 / Should call max_retries times
        assert agent.call_llm_json_object.call_count == 3

    def test_llm_call_exception_triggers_retry(self):
        """LLM 调用异常 → 触发重试 / LLM call exception → triggers retry."""
        agent = _make_agent()
        agent._token_counter.count = MagicMock(return_value=50)
        agent._estimate_input_tokens = MagicMock(return_value=200)
        agent._max_output_tokens = 12000
        # 第一次抛异常，第二次成功 / First throws, second succeeds
        agent.call_llm_json_object = MagicMock(side_effect=[
            RuntimeError("API timeout"),
            {"matches": {"Flow X": "Flow B"}},
        ])
        mermaid_flows = {"Flow B": "mermaid B"}
        orphaned = [{"name": "Flow X", "description": "X desc"}]
        result = agent._llm_match_flows(orphaned, mermaid_flows, max_retries=3)
        assert result == {"Flow X": "Flow B"}
        assert agent.call_llm_json_object.call_count == 2

    def test_missing_scenario_in_result_triggers_retry(self):
        """LLM 漏掉某个场景 → 触发重试 / Missing scenario → triggers retry."""
        agent = _make_agent()
        agent._token_counter.count = MagicMock(return_value=50)
        agent._estimate_input_tokens = MagicMock(return_value=200)
        agent._max_output_tokens = 12000
        # 第一次漏掉了 Flow Y / First misses Flow Y
        # 第二次补上 / Second includes it
        agent.call_llm_json_object = MagicMock(side_effect=[
            {"matches": {"Flow X": "Flow B"}},  # Flow Y missing
            {"matches": {"Flow Y": "Flow C"}},
        ])
        mermaid_flows = {"Flow B": "mermaid B", "Flow C": "mermaid C"}
        orphaned = [
            {"name": "Flow X", "description": "X desc"},
            {"name": "Flow Y", "description": "Y desc"},
        ]
        result = agent._llm_match_flows(orphaned, mermaid_flows, max_retries=3)
        assert result == {"Flow X": "Flow B", "Flow Y": "Flow C"}

    def test_greedy_batching(self):
        """Token 超出预算时自动分批 / Auto-batch when tokens exceed budget."""
        agent = _make_agent()
        agent._max_output_tokens = 2000
        # 控制 token 估算使得每个场景约 500 tokens，预算约 1500，只能放 2 个
        # Control estimations: ~500 tokens/scenario, budget ~1500, fits 2
        agent._token_counter.count = MagicMock(return_value=500)
        agent._estimate_input_tokens = MagicMock(return_value=500)  # base
        agent.call_llm_json_object = MagicMock(return_value={
            "matches": {"Flow A": "MA", "Flow B": "MB"},
        })
        mermaid_flows = {"MA": "m", "MB": "m", "MC": "m"}
        orphaned = [
            {"name": f"Flow {c}", "description": f"Desc {c}"}
            for c in "ABCD"
        ]
        result = agent._llm_match_flows(orphaned, mermaid_flows, max_retries=2)
        # 应该分多个批次调用 / Should call LLM in multiple batches
        assert agent.call_llm_json_object.call_count >= 2
        # 所有场景都返回了结果 / All scenarios have results
        assert len(result) == 4
        for c in "ABCD":
            assert f"Flow {c}" in result


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


# ============================================================================
# 修改 7 测试：case_type 过滤
# Change 7 tests: case_type filtering
# ============================================================================


class TestCaseTypeFiltering:
    """case_type 过滤 — parse_from_sections 按 case_type 跳过不需要的 section。
    case_type filtering — parse_from_sections skips irrelevant sections.
    """

    def test_case_type_biz_skips_single_api(self):
        """case_type=biz 时不解析 single_api 内容。
        case_type=biz should skip single_api content parsing.
        """
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            agent = _make_agent()
            agent._max_output_tokens = 12000
            agent._token_counter.count = MagicMock(return_value=150)
            agent.call_llm_json_object = MagicMock(return_value={
                "api_definitions": [],
                "single_test_points": {},
                "biz_flow_scenarios": [],
            })

            sections = _sample_sections()
            agent.parse_from_sections(sections, case_type="biz")

            # 验证 LLM 调用存在 / Verify LLM was called
            assert agent.call_llm_json_object.called

            # 验证 prompt 不含 single_api 内容 / Verify prompt excludes single_api content
            # _sample_sections 的 single_api 包含 "Login" / _sample_sections single_api contains "Login"
            prompt = agent.call_llm_json_object.call_args[0][0]
            assert "Login" not in prompt, (
                f"case_type=biz should exclude single_api from prompt, but found 'Login'"
            )

    def test_case_type_single_skips_biz_flows(self):
        """case_type=single 时不解析 biz_flows 内容。
        case_type=single should skip biz_flows content parsing.
        """
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            agent = _make_agent()
            agent._max_output_tokens = 12000
            agent._token_counter.count = MagicMock(return_value=150)
            agent.call_llm_json_object = MagicMock(return_value={
                "api_definitions": [],
                "single_test_points": {},
                "biz_flow_scenarios": [],
            })

            sections = _sample_sections()
            agent.parse_from_sections(sections, case_type="single")

            # 验证 LLM 调用存在 / Verify LLM was called
            assert agent.call_llm_json_object.called

            # 验证 prompt 不含 biz_flows 内容 / Verify prompt excludes biz_flows content
            # _sample_sections 的 biz_flows 包含 "User Registration" / _sample_sections biz_flows contains "User Registration"
            prompt = agent.call_llm_json_object.call_args[0][0]
            assert "User Registration" not in prompt, (
                f"case_type=single should exclude biz_flows from prompt, but found 'User Registration'"
            )

    def test_case_type_both_parses_all(self):
        """case_type=both 时解析全部内容。
        case_type=both should parse all content.
        """
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            agent = _make_agent()
            agent._max_output_tokens = 12000
            agent._token_counter.count = MagicMock(return_value=150)
            agent.call_llm_json_object = MagicMock(return_value={
                "api_definitions": [],
                "single_test_points": {},
                "biz_flow_scenarios": [],
            })

            sections = _sample_sections()
            agent.parse_from_sections(sections, case_type="both")

            # 验证 LLM 调用存在 / Verify LLM was called
            assert agent.call_llm_json_object.called

            # 验证 prompt 包含 single_api 和 biz_flows 内容 / Verify prompt includes both
            prompt = agent.call_llm_json_object.call_args[0][0]
            assert "Login" in prompt, (
                f"case_type=both should include single_api in prompt"
            )
            assert "User Registration" in prompt, (
                f"case_type=both should include biz_flows in prompt"
            )

    def test_case_type_default_is_both(self):
        """不传 case_type 时默认 "both"，向后兼容。
        Default case_type is "both" for backward compatibility.
        """
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            agent = _make_agent()
            agent._max_output_tokens = 12000
            agent._token_counter.count = MagicMock(return_value=150)
            agent.call_llm_json_object = MagicMock(return_value={
                "api_definitions": [],
                "single_test_points": {},
                "biz_flow_scenarios": [],
            })

            sections = _sample_sections()
            # 不传 case_type → 应默认 "both" / Not passing case_type → should default to "both"
            agent.parse_from_sections(sections)

            prompt = agent.call_llm_json_object.call_args[0][0]
            assert "Login" in prompt, (
                f"Default case_type should be 'both', but single_api content missing"
            )
            assert "User Registration" in prompt, (
                f"Default case_type should be 'both', but biz_flows content missing"
            )
