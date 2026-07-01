"""Tests for count validation in skeleton generators, data fillers, and assertion generators.

All LLM calls are mocked — NO real API calls.
"""

from unittest.mock import MagicMock, patch

import pytest

from agents.base import BaseAgent
from agents.skeleton_generator import SingleSkeletonGenerator, BizSkeletonGenerator
from config.settings import Settings
from plugins.official.agents.assertion_generator import (
    SingleAssertionGenerator,
    BizAssertionGenerator,
)
from plugins.official.agents.data_filler import SingleDataFiller, BizDataFiller


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_settings():
    """Create a minimal Settings object for testing."""
    return Settings(llm_api_key="test")


def _prevent_real_client():
    """Set a mock shared client so BaseAgent.__init__ does not create a real
    OpenAI client."""
    BaseAgent._shared_client = MagicMock()


def _make_agent(cls, settings=None):
    """Instantiate an agent class with safe defaults and no real LLM client."""
    _prevent_real_client()
    if settings is None:
        settings = _make_settings()
    return cls(settings)


def _mock_call_llm_json(agent, side_effect):
    """Replace agent.call_llm_json with a MagicMock that has the given side_effect."""
    mock = MagicMock()
    mock.side_effect = side_effect
    agent.call_llm_json = mock
    return mock


def _mock_plan_single(num_points):
    """Create a mock plan with single_test_points yielding *num_points* total points."""

    class _Point:
        def __init__(self, tag, test_id, description, scenario_type):
            self.tag = tag
            self.test_id = test_id
            self.description = description
            self.scenario_type = scenario_type

    plan = MagicMock()
    plan.business_summary = "Test business understanding"
    points = [
        _Point("P0", f"t{i}", f"description {i}", "normal")
        for i in range(num_points)
    ]
    plan.single_test_points = {"api_main": points}
    return plan


def _mock_plan_biz(num_scenarios):
    """Create a mock plan with biz_flow_scenarios."""
    plan = MagicMock()
    plan.business_summary = "Test biz understanding"
    plan.biz_flow_scenarios = [
        {"name": f"flow_{i}", "description": f"desc_{i}"}
        for i in range(num_scenarios)
    ]
    plan.mermaid_flows = {}
    return plan


def _valid_single_skeletons(count):
    """Return a response dict with the correct count of single skeletons."""
    return {"single_skeletons": [{"test_id": f"t{i}"} for i in range(count)]}


def _valid_biz_skeletons(count):
    """Return a response dict with the correct count of biz skeletons."""
    return {"biz_skeletons": [{"name": f"flow_{i}", "steps": []} for i in range(count)]}


def _valid_cases(count):
    """Return a response dict with the correct count of cases."""
    return {"cases": [{"test_id": f"t{i}"} for i in range(count)]}


def _valid_biz_flows(count):
    """Return a response dict with the correct count of biz flows."""
    return {"biz_flows": [{"name": f"flow_{i}", "steps": []} for i in range(count)]}


# ---------------------------------------------------------------------------
# SingleSkeletonCountValidationTest
# ---------------------------------------------------------------------------

class SingleSkeletonCountValidationTest:
    """Count validation tests for SingleSkeletonGenerator.generate()."""

    def should_return_skeletons_when_count_matches(self):
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            agent = _make_agent(SingleSkeletonGenerator)
            plan = _mock_plan_single(3)
            _mock_call_llm_json(agent, [_valid_single_skeletons(3)])

            result = agent.generate(plan, interfaces=[])

            assert len(result) == 3
            assert agent.call_llm_json.call_count == 1

    def should_retry_on_mismatch_then_succeed(self):
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            agent = _make_agent(SingleSkeletonGenerator)
            plan = _mock_plan_single(3)
            _mock_call_llm_json(agent, [
                {"single_skeletons": [{"test_id": "x"}]},  # wrong count
                _valid_single_skeletons(3),                # correct on retry
            ])

            result = agent.generate(plan, interfaces=[])

            assert len(result) == 3
            assert agent.call_llm_json.call_count == 2

    def should_raise_valueerror_when_all_retries_exhausted(self):
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            agent = _make_agent(SingleSkeletonGenerator)
            plan = _mock_plan_single(3)
            # Always return wrong count
            _mock_call_llm_json(agent, [
                {"single_skeletons": [{"test_id": "x"}]}
                for _ in range(Settings().max_retries + 1)
            ])

            with pytest.raises(ValueError, match="count validation failed"):
                agent.generate(plan, interfaces=[])


# ---------------------------------------------------------------------------
# BizSkeletonCountValidationTest
# ---------------------------------------------------------------------------

class BizSkeletonCountValidationTest:
    """Count validation tests for BizSkeletonGenerator.generate()."""

    def should_return_skeletons_when_count_matches(self):
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            agent = _make_agent(BizSkeletonGenerator)
            plan = _mock_plan_biz(2)
            _mock_call_llm_json(agent, [_valid_biz_skeletons(2)])

            result = agent.generate(plan, interfaces=[])

            assert len(result) == 2
            assert agent.call_llm_json.call_count == 1

    def should_retry_on_mismatch_then_succeed(self):
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            agent = _make_agent(BizSkeletonGenerator)
            plan = _mock_plan_biz(2)
            _mock_call_llm_json(agent, [
                {"biz_skeletons": []},          # wrong count
                _valid_biz_skeletons(2),        # correct on retry
            ])

            result = agent.generate(plan, interfaces=[])

            assert len(result) == 2
            assert agent.call_llm_json.call_count == 2

    def should_raise_valueerror_when_all_retries_exhausted(self):
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            agent = _make_agent(BizSkeletonGenerator)
            plan = _mock_plan_biz(2)
            _mock_call_llm_json(agent, [
                {"biz_skeletons": []}
                for _ in range(Settings().max_retries + 1)
            ])

            with pytest.raises(ValueError, match="count validation failed"):
                agent.generate(plan, interfaces=[])


# ---------------------------------------------------------------------------
# DataFillerCountValidationTest
# ---------------------------------------------------------------------------

class DataFillerCountValidationTest:
    """Count validation tests for SingleDataFiller and BizDataFiller fill_batch()."""

    def should_return_cases_when_count_matches(self):
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            agent = _make_agent(SingleDataFiller)
            skeletons = [{"test_id": "t1"}, {"test_id": "t2"}]
            _mock_call_llm_json(agent, [_valid_cases(2)])

            result = agent.fill_batch(skeletons, interfaces=[])

            assert len(result) == 2
            assert agent.call_llm_json.call_count == 1

    def should_retry_on_mismatch_then_succeed(self):
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            agent = _make_agent(SingleDataFiller)
            skeletons = [{"test_id": "t1"}, {"test_id": "t2"}]
            _mock_call_llm_json(agent, [
                {"cases": [{"test_id": "x"}]},  # wrong count (1 != 2)
                _valid_cases(2),                # correct on retry
            ])

            result = agent.fill_batch(skeletons, interfaces=[])

            assert len(result) == 2
            assert agent.call_llm_json.call_count == 2

    def should_raise_valueerror_when_all_retries_exhausted(self):
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            agent = _make_agent(SingleDataFiller)
            skeletons = [{"test_id": "t1"}, {"test_id": "t2"}]
            _mock_call_llm_json(agent, [
                {"cases": [{"test_id": "x"}]}
                for _ in range(Settings().max_retries + 1)
            ])

            with pytest.raises(ValueError, match="count validation failed"):
                agent.fill_batch(skeletons, interfaces=[])


# ---------------------------------------------------------------------------
# AssertionGeneratorCountValidationTest
# ---------------------------------------------------------------------------

class AssertionGeneratorCountValidationTest:
    """Count validation tests for SingleAssertionGenerator and BizAssertionGenerator fill_batch()."""

    def should_return_cases_when_count_matches(self):
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            agent = _make_agent(SingleAssertionGenerator)
            cases = [{"test_id": "t1"}, {"test_id": "t2"}, {"test_id": "t3"}]
            _mock_call_llm_json(agent, [_valid_cases(3)])

            result = agent.fill_batch(cases, interfaces=[])

            assert len(result) == 3
            assert agent.call_llm_json.call_count == 1

    def should_retry_on_mismatch_then_succeed(self):
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            agent = _make_agent(SingleAssertionGenerator)
            cases = [{"test_id": "t1"}, {"test_id": "t2"}, {"test_id": "t3"}]
            _mock_call_llm_json(agent, [
                {"cases": []},      # wrong count
                _valid_cases(3),    # correct on retry
            ])

            result = agent.fill_batch(cases, interfaces=[])

            assert len(result) == 3
            assert agent.call_llm_json.call_count == 2

    def should_raise_valueerror_when_all_retries_exhausted(self):
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            agent = _make_agent(SingleAssertionGenerator)
            cases = [{"test_id": "t1"}, {"test_id": "t2"}, {"test_id": "t3"}]
            _mock_call_llm_json(agent, [
                {"cases": []}
                for _ in range(Settings().max_retries + 1)
            ])

            with pytest.raises(ValueError, match="count validation failed"):
                agent.fill_batch(cases, interfaces=[])


# ---------------------------------------------------------------------------
# UrlCorrectionCountValidationTest
# ---------------------------------------------------------------------------

class UrlCorrectionCountValidationTest:
    """Count validation tests for SingleSkeletonGenerator.correct_urls()."""

    def should_return_corrected_when_count_matches(self):
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            agent = _make_agent(SingleSkeletonGenerator)
            bad_cases = [
                {"test_id": "t1", "url": "/bad/1", "api_name": "api1",
                 "method": "GET", "relevance_id": "if1"},
                {"test_id": "t2", "url": "/bad/2", "api_name": "api2",
                 "method": "POST", "relevance_id": "if2"},
            ]
            interfaces = [
                {"test_id": "if1", "api_name": "api1", "method": "GET", "url": "/good/1"},
                {"test_id": "if2", "api_name": "api2", "method": "POST", "url": "/good/2"},
            ]
            _mock_call_llm_json(agent, [
                {"cases": [
                    {"test_id": "t1", "url": "/good/1"},
                    {"test_id": "t2", "url": "/good/2"},
                ]},
            ])

            result = agent.correct_urls(bad_cases, interfaces, api_doc_text="/good/1\n/good/2")

            assert len(result) == 2
            assert agent.call_llm_json.call_count == 1

    def should_retry_on_mismatch_then_succeed(self):
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            agent = _make_agent(SingleSkeletonGenerator)
            bad_cases = [
                {"test_id": "t1", "url": "/bad/1", "api_name": "api1",
                 "method": "GET", "relevance_id": "if1"},
            ]
            interfaces = [
                {"test_id": "if1", "api_name": "api1", "method": "GET", "url": "/good/1"},
            ]
            _mock_call_llm_json(agent, [
                {"cases": []},                                              # empty on first try
                {"cases": [{"test_id": "t1", "url": "/good/1"}]},          # correct on retry
            ])

            result = agent.correct_urls(bad_cases, interfaces, api_doc_text="/good/1")

            assert len(result) == 1
            assert agent.call_llm_json.call_count == 2

    def should_fallback_to_original_when_all_retries_exhaust(self):
        """URL correction falls back to original bad_cases instead of raising."""
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            agent = _make_agent(SingleSkeletonGenerator)
            bad_cases = [
                {"test_id": "t1", "url": "/bad/1", "api_name": "api1",
                 "method": "GET", "relevance_id": "if1"},
                {"test_id": "t2", "url": "/bad/2", "api_name": "api2",
                 "method": "POST", "relevance_id": "if2"},
            ]
            interfaces = [
                {"test_id": "if1", "api_name": "api1", "method": "GET", "url": "/good/1"},
                {"test_id": "if2", "api_name": "api2", "method": "POST", "url": "/good/2"},
            ]
            # Always return wrong count
            _mock_call_llm_json(agent, [
                {"cases": []}
                for _ in range(Settings().max_retries + 1)
            ])

            result = agent.correct_urls(bad_cases, interfaces, api_doc_text="/good/1\n/good/2")

            # Should fall back to original bad_cases, not raise
            assert result is bad_cases


# ---------------------------------------------------------------------------
# Skeleton count validation — warn/skip strategy integration tests
# 骨架数量校验 — warn/skip 策略集成测试
# ---------------------------------------------------------------------------

class SingleSkeletonCountWarnSkipTest:
    """Count validation with warn/skip strategies for SingleSkeletonGenerator."""

    def should_return_partial_results_on_warn_strategy(self):
        """warn 策略下数量不匹配返回不完整结果 / Returns partial results on warn."""
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            settings = _make_settings()
            settings.validation_rules = [
                {"check": "skeleton_count", "strategy": "warn"},
            ]
            agent = _make_agent(SingleSkeletonGenerator, settings=settings)
            plan = _mock_plan_single(3)
            # 始终返回错误数量 / always return wrong count
            _mock_call_llm_json(agent, [
                {"single_skeletons": [{"test_id": "x"}]}
                for _ in range(Settings().max_retries + 1)
            ])

            result = agent.generate(plan, interfaces=[])
            # warn 策略：不抛异常，返回不完整结果 / accepts partial
            assert len(result) == 1

    def should_skip_count_check_on_skip_strategy(self):
        """skip 策略下不重试直接返回 / No retries on skip strategy."""
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            settings = _make_settings()
            settings.validation_rules = [
                {"check": "skeleton_count", "strategy": "skip"},
            ]
            agent = _make_agent(SingleSkeletonGenerator, settings=settings)
            plan = _mock_plan_single(3)
            _mock_call_llm_json(agent, [
                {"single_skeletons": [{"test_id": "x"}]},
            ])

            result = agent.generate(plan, interfaces=[])
            # skip 策略：不做校验，直接返回 / bypasses check
            assert len(result) == 1
            # 只调一次 LLM（不重试）/ only one LLM call (no retries)
            assert agent.call_llm_json.call_count == 1


class BizSkeletonCountWarnSkipTest:
    """Count validation with warn/skip strategies for BizSkeletonGenerator."""

    def should_return_partial_results_on_warn_strategy(self):
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            settings = _make_settings()
            settings.validation_rules = [
                {"check": "skeleton_count", "strategy": "warn"},
            ]
            agent = _make_agent(BizSkeletonGenerator, settings=settings)
            plan = _mock_plan_biz(2)
            _mock_call_llm_json(agent, [
                {"biz_skeletons": []}
                for _ in range(Settings().max_retries + 1)
            ])

            result = agent.generate(plan, interfaces=[])
            assert len(result) == 0  # 接受不完整 / accepts empty


class DataFillerCountWarnTest:
    """Count validation with warn strategy for data fillers."""

    def should_return_partial_results_on_warn_strategy(self):
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            settings = _make_settings()
            settings.validation_rules = [
                {"check": "data_fill_count", "strategy": "warn"},
            ]
            agent = _make_agent(SingleDataFiller, settings=settings)
            skeletons = [{"test_id": "t1"}, {"test_id": "t2"}]
            _mock_call_llm_json(agent, [
                {"cases": [{"test_id": "x"}]}
                for _ in range(Settings().max_retries + 1)
            ])

            result = agent.fill_batch(skeletons, interfaces=[])
            assert len(result) == 1  # 接受不完整 / accepts partial


class AssertionGeneratorCountWarnTest:
    """Count validation with warn strategy for assertion generators."""

    def should_return_partial_results_on_warn_strategy(self):
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            settings = _make_settings()
            settings.validation_rules = [
                {"check": "assertion_count", "strategy": "warn"},
            ]
            agent = _make_agent(SingleAssertionGenerator, settings=settings)
            cases = [{"test_id": "t1"}, {"test_id": "t2"}, {"test_id": "t3"}]
            _mock_call_llm_json(agent, [
                {"cases": []}
                for _ in range(Settings().max_retries + 1)
            ])

            result = agent.fill_batch(cases, interfaces=[])
            assert len(result) == 0  # 接受不完整 / accepts empty
