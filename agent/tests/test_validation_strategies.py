"""Tests for validation strategy configuration and _count_validate behavior.
校验策略配置和 _count_validate 行为测试。

All LLM calls are mocked — NO real API calls.
"""

from unittest.mock import MagicMock, patch

import pytest

from agents.base import BaseAgent
from agents.skeleton_generator import SingleSkeletonGenerator, _count_validate
from config.settings import Settings, get_strategy, _parse_validation_rules


# ---------------------------------------------------------------------------
# Shared helpers / 共享辅助函数
# ---------------------------------------------------------------------------

def _make_settings(**kwargs):
    """创建测试用 Settings / Create a minimal Settings object for testing."""
    s = Settings(llm_api_key="test")
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


# ---------------------------------------------------------------------------
# get_strategy tests / get_strategy 查询测试
# ---------------------------------------------------------------------------

class TestGetStrategy:
    """Tests for get_strategy() utility function."""

    def should_return_strategy_for_existing_check(self):
        """存在的 check 返回对应策略 / Returns strategy for existing check."""
        rules = [{"check": "skeleton_count", "strategy": "warn"}]
        assert get_strategy(rules, "skeleton_count") == "warn"

    def should_return_default_when_check_not_found(self):
        """不存在的 check 返回默认 fail / Returns default fail when not found."""
        rules = [{"check": "skeleton_count", "strategy": "fail"}]
        assert get_strategy(rules, "nonexistent") == "fail"
        assert get_strategy(rules, "nonexistent", default="skip") == "skip"

    def should_return_default_for_empty_rules(self):
        """空规则列表返回默认值 / Returns default for empty rules list."""
        assert get_strategy([], "skeleton_count") == "fail"

    def should_match_first_matching_check(self):
        """多个同名校验时返回第一个匹配 / Returns first match when duplicates."""
        rules = [
            {"check": "count", "strategy": "warn"},
            {"check": "count", "strategy": "fail"},
        ]
        assert get_strategy(rules, "count") == "warn"


# ---------------------------------------------------------------------------
# _parse_validation_rules tests / 规则解析测试
# ---------------------------------------------------------------------------

class TestParseValidationRules:
    """Tests for _parse_validation_rules() in settings.py."""

    def should_parse_list_format(self):
        """解析 list 格式 / Parses list format."""
        result = _parse_validation_rules([
            {"check": "skel", "strategy": "fail"},
        ])
        assert len(result) == 1
        assert result[0] == {"check": "skel", "strategy": "fail"}

    def should_parse_dict_format(self):
        """解析 dict 格式（兼容旧配置）/ Parses dict format (backward compat)."""
        result = _parse_validation_rules({"skel": "warn", "url": "skip"})
        assert len(result) == 2
        assert {"check": "skel", "strategy": "warn"} in result
        assert {"check": "url", "strategy": "skip"} in result

    def should_return_empty_list_for_none(self):
        """None 输入返回空列表 / Returns empty list for None."""
        assert _parse_validation_rules(None) == []

    def should_return_empty_list_for_empty_dict(self):
        """空 dict 返回空列表 / Returns empty list for empty dict."""
        assert _parse_validation_rules({}) == []


# ---------------------------------------------------------------------------
# _count_validate strategy behavior / _count_validate 策略行为测试
# ---------------------------------------------------------------------------

class TestCountValidateStrategies:
    """Tests for _count_validate() with different strategies."""

    def should_return_items_when_count_matches(self):
        """数量匹配时直接返回 / Returns items when count matches."""
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            agent = _make_agent()
            mock = MagicMock()
            mock.return_value = {"items": [1, 2, 3]}
            agent.call_llm_json = mock

            result = _count_validate(agent, "prompt", "sys", "items", 3, "test", "fail")
            assert len(result) == 3
            assert agent.call_llm_json.call_count == 1

    def should_retry_on_mismatch_then_succeed(self):
        """数量不匹配时重试后成功 / Retries on mismatch then succeeds."""
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            agent = _make_agent()
            mock = MagicMock()
            mock.side_effect = [
                {"items": [1]},         # 数量不对 → 重试 / wrong count → retry
                {"items": [1, 2, 3]},   # 正确 / correct
            ]
            agent.call_llm_json = mock

            result = _count_validate(agent, "prompt", "sys", "items", 3, "test", "fail")
            assert len(result) == 3
            assert agent.call_llm_json.call_count == 2

    def should_raise_valueerror_on_fail_strategy(self):
        """fail 策略下耗尽重试抛异常 / Raises ValueError on fail strategy."""
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            agent = _make_agent()
            mock = MagicMock()
            mock.return_value = {"items": [1]}  # 始终数量不对 / always wrong count
            agent.call_llm_json = mock

            with pytest.raises(ValueError, match="count validation failed"):
                _count_validate(agent, "prompt", "sys", "items", 3, "test", "fail")

    def should_return_items_on_warn_strategy_when_exhausted(self):
        """warn 策略下耗尽重试返回不完整结果 / Returns partial results on warn."""
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            agent = _make_agent()
            mock = MagicMock()
            mock.return_value = {"items": [1, 2]}  # expected 3, got 2
            agent.call_llm_json = mock

            result = _count_validate(agent, "prompt", "sys", "items", 3, "test", "warn")
            # 接受不完整结果 / accepts partial results
            assert len(result) == 2
            # 所有重试都调用了 / all retries were called
            assert agent.call_llm_json.call_count == agent._max_retries + 1

    def should_return_items_on_skip_strategy(self):
        """skip 策略下不重试直接返回 / No retries on skip strategy."""
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            agent = _make_agent()
            mock = MagicMock()
            mock.return_value = {"items": [1]}  # expected 3, got 1
            agent.call_llm_json = mock

            result = _count_validate(agent, "prompt", "sys", "items", 3, "test", "skip")
            assert len(result) == 1
            # 只调一次，不重试 / only one call, no retries
            assert agent.call_llm_json.call_count == 1

    def should_stop_retry_early_when_count_matches(self):
        """数量匹配后立即停止重试 / Stops retrying immediately on match."""
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            agent = _make_agent()
            call_count = [0]
            # max_retries=3, but should stop after first call
            mock = MagicMock()
            mock.return_value = {"items": [1, 2]}
            agent.call_llm_json = mock

            result = _count_validate(agent, "prompt", "sys", "items", 2, "test", "fail")
            assert len(result) == 2
            assert agent.call_llm_json.call_count == 1


# ---------------------------------------------------------------------------
# Settings default validation_rules / 默认校验规则测试
# ---------------------------------------------------------------------------

class TestDefaultValidationRules:
    """Tests for default validation_rules in Settings."""

    def should_have_default_rules(self):
        """Settings 创建后应有默认 4 条规则 / Default Settings has 4 rules."""
        s = Settings()
        assert len(s.validation_rules) == 4

    def should_default_skeleton_count_to_fail(self):
        """骨架数量校验默认 fail / Skeleton count defaults to fail."""
        s = Settings()
        assert get_strategy(s.validation_rules, "skeleton_count") == "fail"

    def should_default_url_check_to_warn(self):
        """URL 校验默认 warn / URL check defaults to warn."""
        s = Settings()
        assert get_strategy(s.validation_rules, "url_check") == "warn"

    def should_default_data_fill_count_to_fail(self):
        """数据填充数量校验默认 fail / Data fill count defaults to fail."""
        s = Settings()
        assert get_strategy(s.validation_rules, "data_fill_count") == "fail"

    def should_default_assertion_count_to_fail(self):
        """断言数量校验默认 fail / Assertion count defaults to fail."""
        s = Settings()
        assert get_strategy(s.validation_rules, "assertion_count") == "fail"
