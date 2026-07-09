"""Tests for BatchController — plugin pipeline orchestration."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agents.batch_controller import BatchController
from config.settings import Settings
from plugins.base import CaseAttributeGenerator, PluginDeclaration


def _make_settings(**kwargs):
    s = Settings()
    s.llm_api_key = "test"
    s.plugin_batch_size = kwargs.get("batch_size", 2)
    s.enable_validation = kwargs.get("enable_validation", False)
    s.max_validation_retries = kwargs.get("max_validation_retries", 1)
    s.max_steps_no_progress = kwargs.get("max_steps_no_progress", 10)
    s.url_correction_max_retries = kwargs.get("url_correction_max_retries", 3)
    s.consecutive_batch_failure_limit = kwargs.get("consecutive_batch_failure_limit", 3)
    s.llm_rate_limit_delay = kwargs.get("llm_rate_limit_delay", 0.0)
    return s


def _make_mock_plugin(name="test_plugin", applies_single=True, applies_biz=True,
                      max_retries=1, error_strategy="skip"):
    plugin = MagicMock(spec=CaseAttributeGenerator)
    decl = PluginDeclaration(
        plugin_name=name,
        attributes=[],
        applies_to_single=applies_single,
        applies_to_biz=applies_biz,
        max_retries=max_retries,
        error_strategy=error_strategy,
    )
    type(plugin).declaration = decl
    return plugin


def _make_mock_plan(single_count=2, biz_count=1):
    plan = MagicMock()
    plan.business_summary = "Test plan"
    plan.single_test_points = {
        f"api{i}": [MagicMock(test_id=f"t{i}_{j}", tag="P0",
                               description=f"Test {j}", scenario_type="positive")
                    for j in range(single_count // 2 + 1)]
        for i in range(1, 3)
    } if single_count > 0 else {}
    plan.biz_flow_scenarios = [
        {"name": f"flow{i}", "description": f"Biz flow {i}"}
        for i in range(1, biz_count + 1)
    ] if biz_count > 0 else []
    return plan


# ---------------------------------------------------------------------------
# BatchController.run() tests
# ---------------------------------------------------------------------------

class TestBatchControllerRun:
    """Tests for BatchController.run() main pipeline."""

    def should_generate_skeletons_and_run_plugins(self):
        settings = _make_settings()
        controller = BatchController(settings)

        plan = _make_mock_plan(single_count=2, biz_count=1)
        plan.single_test_points = {
            "api1": [MagicMock(test_id="t1", tag="P0")],
        }
        plan.biz_flow_scenarios = []

        mock_single_gen = MagicMock()
        mock_single_gen.generate.return_value = [{"test_id": "t1", "url": "/api/test"}]
        mock_biz_gen = MagicMock()
        mock_biz_gen.generate.return_value = []

        plugin = _make_mock_plugin(name="data_filling", applies_biz=False)
        plugin.generate.return_value = [{"test_id": "t1", "url": "/api/test", "filled": True}]

        with tempfile.TemporaryDirectory() as tmpdir:
            result = controller.run(
                plan=plan,
                interfaces=[{"test_id": "t1", "method": "GET", "url": "/api/test"}],
                output_dir=tmpdir,
                single_skel_gen=mock_single_gen,
                biz_skel_gen=mock_biz_gen,
                plugins=[plugin],
                user_guidance="",
                api_doc_text="",
            )

        assert len(result["single_cases"]) == 1
        assert result["single_cases"][0]["filled"] is True
        assert len(result["biz_flows"]) == 0

    def should_skip_biz_when_no_scenarios(self):
        settings = _make_settings()
        controller = BatchController(settings)

        plan = _make_mock_plan(single_count=1, biz_count=0)
        plan.single_test_points = {"api1": [MagicMock(test_id="t1", tag="P0")]}
        plan.biz_flow_scenarios = []

        mock_single_gen = MagicMock()
        mock_single_gen.generate.return_value = [{"test_id": "t1", "url": "/api/test"}]
        mock_biz_gen = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            result = controller.run(
                plan=plan,
                interfaces=[{"test_id": "t1", "method": "GET", "url": "/api/test"}],
                output_dir=tmpdir,
                single_skel_gen=mock_single_gen,
                biz_skel_gen=mock_biz_gen,
                plugins=[],
                api_doc_text="",
            )

        mock_biz_gen.generate.assert_not_called()
        assert len(result["biz_flows"]) == 0

    def should_start_from_scratch_when_no_checkpoint(self):
        settings = _make_settings()
        controller = BatchController(settings)

        plan = _make_mock_plan(single_count=1, biz_count=0)
        plan.single_test_points = {"api1": [MagicMock(test_id="t1", tag="P0")]}
        plan.biz_flow_scenarios = []

        mock_single_gen = MagicMock()
        mock_single_gen.generate.return_value = [{"test_id": "t1", "url": "/api/test"}]
        mock_biz_gen = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            result = controller.run(
                plan=plan,
                interfaces=[{"test_id": "t1", "method": "GET", "url": "/api/test"}],
                output_dir=tmpdir,
                single_skel_gen=mock_single_gen,
                biz_skel_gen=mock_biz_gen,
                plugins=[],
                resume=True,
                memory_dir=str(Path(tmpdir) / "nonexistent"),
                api_doc_text="",
            )

        mock_single_gen.generate.assert_called_once()
        assert len(result["single_cases"]) == 1


# ---------------------------------------------------------------------------
# _apply_plugin tests
# ---------------------------------------------------------------------------

class TestApplyPlugin:
    """Tests for BatchController._apply_plugin()."""

    def should_succeed_on_first_attempt(self):
        settings = _make_settings()
        controller = BatchController(settings)

        plugin = _make_mock_plugin(name="test", error_strategy="fail")
        cases = [{"test_id": "t1"}, {"test_id": "t2"}]
        plugin.generate.return_value = [
            {"test_id": "t1", "extra": True},
            {"test_id": "t2", "extra": True},
        ]

        result = controller._apply_plugin(plugin, cases, [], [], "")
        assert len(result) == 2
        assert result[0]["extra"] is True

    def should_retry_on_failure_then_succeed(self):
        settings = _make_settings()
        controller = BatchController(settings)

        plugin = _make_mock_plugin(name="test", max_retries=3, error_strategy="fail")
        cases = [{"test_id": "t1"}]
        plugin.generate.side_effect = [
            Exception("first fail"),
            [{"test_id": "t1", "retried": True}],
        ]

        result = controller._apply_plugin(plugin, cases, [], [], "")
        assert len(result) == 1
        assert result[0]["retried"] is True
        assert plugin.generate.call_count == 2

    def should_raise_on_fail_strategy_when_all_retries_exhausted(self):
        settings = _make_settings()
        controller = BatchController(settings)

        plugin = _make_mock_plugin(name="test", max_retries=2, error_strategy="fail")
        cases = [{"test_id": "t1"}]
        plugin.generate.side_effect = Exception("persistent failure")

        with pytest.raises(Exception):
            controller._apply_plugin(plugin, cases, [], [], "")

    def should_keep_original_on_warn_strategy(self):
        settings = _make_settings()
        controller = BatchController(settings)

        plugin = _make_mock_plugin(name="test", max_retries=1, error_strategy="warn")
        cases = [{"test_id": "t1"}]
        plugin.generate.side_effect = Exception("fail")

        result = controller._apply_plugin(plugin, cases, [], [], "")
        assert result == cases

    def should_keep_original_on_skip_strategy(self):
        settings = _make_settings()
        controller = BatchController(settings)

        plugin = _make_mock_plugin(name="test", max_retries=1, error_strategy="skip")
        cases = [{"test_id": "t1"}]
        plugin.generate.side_effect = Exception("fail")

        result = controller._apply_plugin(plugin, cases, [], [], "")
        assert result == cases

    def should_process_empty_cases_list(self):
        settings = _make_settings()
        controller = BatchController(settings)

        plugin = _make_mock_plugin()
        result = controller._apply_plugin(plugin, [], [], [], "")
        assert result == []


# ---------------------------------------------------------------------------
# URL check and correct tests
# ---------------------------------------------------------------------------

class TestUrlCheckAndCorrect:
    """Tests for BatchController._url_check_and_correct()."""

    def should_return_all_when_no_api_doc(self):
        settings = _make_settings()
        controller = BatchController(settings)
        mock_agent = MagicMock()

        skeletons = [{"test_id": "t1", "url": "/api/test"}]
        valid, failed = controller._url_check_and_correct(
            skeletons, [], "", None, mock_agent, "single"
        )
        assert len(valid) == 1
        assert len(failed) == 0

    def should_pass_when_all_urls_found(self):
        settings = _make_settings()
        controller = BatchController(settings)
        mock_agent = MagicMock()

        api_doc = "GET /api/test returns data"
        skeletons = [{"test_id": "t1", "url": "/api/test"}]
        valid, failed = controller._url_check_and_correct(
            skeletons, [], api_doc, None, mock_agent, "single"
        )
        assert len(valid) == 1
        assert len(failed) == 0

    def should_correct_invalid_urls(self):
        settings = _make_settings()
        controller = BatchController(settings)
        mock_agent = MagicMock()
        mock_agent.correct_urls.return_value = [{"test_id": "t1", "url": "/api/correct"}]

        api_doc = "GET /api/correct returns data"
        skeletons = [{"test_id": "t1", "url": "/api/wrong"}]
        valid, failed = controller._url_check_and_correct(
            skeletons, [], api_doc, None, mock_agent, "single"
        )
        assert len(valid) == 1
        assert valid[0]["url"] == "/api/correct"

    def should_split_failed_when_correction_exhausted(self):
        settings = _make_settings()
        settings.url_correction_max_retries = 0
        controller = BatchController(settings)
        mock_agent = MagicMock()

        api_doc = "only this text"
        skeletons = [{"test_id": "t1", "url": "/not/found"}]
        valid, failed = controller._url_check_and_correct(
            skeletons, [], api_doc, None, mock_agent, "single"
        )
        assert len(valid) == 0
        assert len(failed) == 1


# ---------------------------------------------------------------------------
# Consecutive failure tests
# ---------------------------------------------------------------------------

class TestConsecutiveFailure:
    """Tests for BatchController._check_consecutive_failures()."""

    def should_continue_when_under_limit(self):
        settings = _make_settings(consecutive_batch_failure_limit=3)
        controller = BatchController(settings)
        assert controller._check_consecutive_failures(2, "test") is False

    def should_stop_when_at_limit(self):
        settings = _make_settings(consecutive_batch_failure_limit=3)
        controller = BatchController(settings)
        assert controller._check_consecutive_failures(3, "test") is True

    def should_stop_when_above_limit(self):
        settings = _make_settings(consecutive_batch_failure_limit=3)
        controller = BatchController(settings)
        assert controller._check_consecutive_failures(5, "test") is True

    def should_never_stop_when_disabled(self):
        settings = _make_settings(consecutive_batch_failure_limit=-1)
        controller = BatchController(settings)
        assert controller._check_consecutive_failures(100, "test") is False


# ---------------------------------------------------------------------------
# Split batches tests
# ---------------------------------------------------------------------------

class TestSplitBatches:
    """Tests for BatchController._split_batches()."""

    def should_return_single_batch_when_size_is_negative_one(self):
        settings = _make_settings(batch_size=-1)
        controller = BatchController(settings)
        items = [1, 2, 3, 4, 5]
        batches = controller._split_batches(items)
        assert len(batches) == 1
        assert len(batches[0]) == 5

    def should_split_into_chunks(self):
        settings = _make_settings(batch_size=2)
        controller = BatchController(settings)
        items = [1, 2, 3, 4, 5]
        batches = controller._split_batches(items)
        assert len(batches) == 3
        assert batches[0] == [1, 2]
        assert batches[1] == [3, 4]
        assert batches[2] == [5]

    def should_handle_empty_list(self):
        settings = _make_settings(batch_size=2)
        controller = BatchController(settings)
        batches = controller._split_batches([])
        assert batches == []


# ---------------------------------------------------------------------------
# URL failure action tests
# ---------------------------------------------------------------------------

class TestUrlFailureAction:
    """Tests for url_failure_action behavior in BatchController."""

    def test_discard_default(self):
        """默认 behaviour: 失败用例进入 all_failures 列表 / Failed cases go to all_failures."""
        from flow_forge_schemas import URL_NOT_EXIST_PREFIX

        settings = _make_settings(url_correction_max_retries=0)
        # 默认 url_check strategy=warn，无 failure_action → discard
        controller = BatchController(settings)

        plan = _make_mock_plan(single_count=1, biz_count=0)
        plan.single_test_points = {"api1": [MagicMock(test_id="t1", tag="P0")]}
        plan.biz_flow_scenarios = []

        mock_single_gen = MagicMock()
        mock_single_gen.generate.return_value = [{"test_id": "t1", "url": "/not/found"}]
        mock_biz_gen = MagicMock()
        mock_biz_gen.generate.return_value = []

        with tempfile.TemporaryDirectory() as tmpdir:
            result = controller.run(
                plan=plan,
                interfaces=[{"test_id": "t1", "method": "GET", "url": "/not/found"}],
                output_dir=tmpdir,
                single_skel_gen=mock_single_gen,
                biz_skel_gen=mock_biz_gen,
                plugins=[],
                api_doc_text="only this text is in the doc",
            )

        assert len(result["failures"]) == 1
        assert len(result["single_cases"]) == 0
        assert result["failures"][0]["reason"] == "URL correction exhausted"

    def test_keep_merges_failed(self):
        """failure_action=keep: 失败用例合并回 single_cases / Failed cases merged back."""
        settings = _make_settings(url_correction_max_retries=0)
        settings.validation_rules = [
            {"check": "url_check", "strategy": "warn", "failure_action": "keep"},
        ]
        controller = BatchController(settings)

        plan = _make_mock_plan(single_count=1, biz_count=0)
        plan.single_test_points = {"api1": [MagicMock(test_id="t1", tag="P0")]}
        plan.biz_flow_scenarios = []

        mock_single_gen = MagicMock()
        mock_single_gen.generate.return_value = [{"test_id": "t1", "url": "/not/found"}]
        mock_biz_gen = MagicMock()
        mock_biz_gen.generate.return_value = []

        with tempfile.TemporaryDirectory() as tmpdir:
            result = controller.run(
                plan=plan,
                interfaces=[{"test_id": "t1", "method": "GET", "url": "/not/found"}],
                output_dir=tmpdir,
                single_skel_gen=mock_single_gen,
                biz_skel_gen=mock_biz_gen,
                plugins=[],
                api_doc_text="only this text is in the doc",
            )

        assert len(result["failures"]) == 0
        assert len(result["single_cases"]) == 1

    def test_keep_url_prefix(self):
        """failure_action=keep: URL 仍有 <URL not exist> 前缀 / URL still has prefix."""
        from flow_forge_schemas import URL_NOT_EXIST_PREFIX

        settings = _make_settings(url_correction_max_retries=0)
        settings.validation_rules = [
            {"check": "url_check", "strategy": "warn", "failure_action": "keep"},
        ]
        controller = BatchController(settings)

        plan = _make_mock_plan(single_count=1, biz_count=0)
        plan.single_test_points = {"api1": [MagicMock(test_id="t1", tag="P0")]}
        plan.biz_flow_scenarios = []

        mock_single_gen = MagicMock()
        mock_single_gen.generate.return_value = [{"test_id": "t1", "url": "/not/found"}]
        mock_biz_gen = MagicMock()
        mock_biz_gen.generate.return_value = []

        with tempfile.TemporaryDirectory() as tmpdir:
            result = controller.run(
                plan=plan,
                interfaces=[{"test_id": "t1", "method": "GET", "url": "/not/found"}],
                output_dir=tmpdir,
                single_skel_gen=mock_single_gen,
                biz_skel_gen=mock_biz_gen,
                plugins=[],
                api_doc_text="only this text is in the doc",
            )

        assert result["single_cases"][0]["url"].startswith(URL_NOT_EXIST_PREFIX)

    def test_final_url_check_no_double_prefix(self):
        """_final_url_check: 已有前缀的 URL 不重复添加 / No double prefix."""
        from flow_forge_schemas import URL_NOT_EXIST_PREFIX

        cases = [{"url": f"{URL_NOT_EXIST_PREFIX}/api/test"}]
        BatchController._final_url_check(cases, "some doc text without that url")
        assert cases[0]["url"] == f"{URL_NOT_EXIST_PREFIX}/api/test"

    def test_final_url_check_adds_prefix_for_new_urls(self):
        """_final_url_check: 新发现的无效 URL 正常添加前缀 / Adds prefix for new invalid URLs."""
        from flow_forge_schemas import URL_NOT_EXIST_PREFIX

        cases = [{"url": "/api/notindoc"}]
        BatchController._final_url_check(cases, "only this text")
        assert cases[0]["url"] == f"{URL_NOT_EXIST_PREFIX}/api/notindoc"
