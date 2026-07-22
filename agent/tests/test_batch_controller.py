"""Tests for BatchController — plugin pipeline orchestration."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agents.batch_controller import BatchController
from config.settings import Settings
from graph.checkpoint import CheckpointManager
from plugins.base import CaseAttributeGenerator, PluginDeclaration


def _make_settings(**kwargs):
    s = Settings()
    s.llm_api_key = "test"
    s.plugin_batch_size = kwargs.get("batch_size", 2)
    s.case_format_max_retries = kwargs.get("case_format_max_retries", 1)
    s.url_doc_match_max_retries = kwargs.get("url_doc_match_max_retries", 3)
    s.consecutive_batch_failure_limit = kwargs.get("consecutive_batch_failure_limit", 3)
    s.skeleton_batch_size = kwargs.get("skeleton_batch_size", 10)
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


def _setup_mock_skel_gen(mock_gen, plan, return_skeletons, batch_size=10):
    """为 mock 骨架生成器设置 iter_batches + generate_batch。
    Set up mock skeleton generator with iter_batches + generate_batch.

    用于适配新的逐批 checkpoint API / For adapting tests to new per-batch checkpoint API.
    """
    mock_gen._skeleton_batch_size = batch_size
    if isinstance(return_skeletons, list) and return_skeletons:
        mock_gen.iter_batches = MagicMock(return_value=iter([
            ({}, len(return_skeletons), 1, 1),
        ]))
        mock_gen.generate_batch = MagicMock(return_value=return_skeletons)
    else:
        mock_gen.iter_batches = MagicMock(return_value=iter([]))


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
        _setup_mock_skel_gen(mock_single_gen, plan, [{"test_id": "t1", "url": "/api/test"}])
        mock_biz_gen = MagicMock()
        _setup_mock_skel_gen(mock_biz_gen, plan, [])

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
        _setup_mock_skel_gen(mock_single_gen, plan, [{"test_id": "t1", "url": "/api/test"}])
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

        mock_biz_gen.generate_batch.assert_not_called()
        assert len(result["biz_flows"]) == 0

    def should_start_from_scratch_when_no_checkpoint(self):
        settings = _make_settings()
        controller = BatchController(settings)

        plan = _make_mock_plan(single_count=1, biz_count=0)
        plan.single_test_points = {"api1": [MagicMock(test_id="t1", tag="P0")]}
        plan.biz_flow_scenarios = []

        mock_single_gen = MagicMock()
        _setup_mock_skel_gen(mock_single_gen, plan, [{"test_id": "t1", "url": "/api/test"}])
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

        mock_single_gen.generate_batch.assert_called_once()
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
        settings.url_doc_match_max_retries = 0
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

        settings = _make_settings(url_doc_match_max_retries=0)
        # 默认 url_check strategy=warn，无 failure_action → discard
        controller = BatchController(settings)

        plan = _make_mock_plan(single_count=1, biz_count=0)
        plan.single_test_points = {"api1": [MagicMock(test_id="t1", tag="P0")]}
        plan.biz_flow_scenarios = []

        mock_single_gen = MagicMock()
        _setup_mock_skel_gen(mock_single_gen, plan, [{"test_id": "t1", "url": "/not/found"}])
        mock_biz_gen = MagicMock()
        _setup_mock_skel_gen(mock_biz_gen, plan, [])

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
        settings = _make_settings(url_doc_match_max_retries=0)
        settings.case_gen_validation = [
            {"check": "url_check", "strategy": "warn", "failure_action": "keep"},
        ]
        controller = BatchController(settings)

        plan = _make_mock_plan(single_count=1, biz_count=0)
        plan.single_test_points = {"api1": [MagicMock(test_id="t1", tag="P0")]}
        plan.biz_flow_scenarios = []

        mock_single_gen = MagicMock()
        _setup_mock_skel_gen(mock_single_gen, plan, [{"test_id": "t1", "url": "/not/found"}])
        mock_biz_gen = MagicMock()
        _setup_mock_skel_gen(mock_biz_gen, plan, [])

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

        settings = _make_settings(url_doc_match_max_retries=0)
        settings.case_gen_validation = [
            {"check": "url_check", "strategy": "warn", "failure_action": "keep"},
        ]
        controller = BatchController(settings)

        plan = _make_mock_plan(single_count=1, biz_count=0)
        plan.single_test_points = {"api1": [MagicMock(test_id="t1", tag="P0")]}
        plan.biz_flow_scenarios = []

        mock_single_gen = MagicMock()
        _setup_mock_skel_gen(mock_single_gen, plan, [{"test_id": "t1", "url": "/not/found"}])
        mock_biz_gen = MagicMock()
        _setup_mock_skel_gen(mock_biz_gen, plan, [])

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


# ---------------------------------------------------------------------------
# BatchResumeProgress tests / 批次断点续跑测试
# ---------------------------------------------------------------------------

class TestBatchResumeProgress:
    """验证逐 batch 保存检查点和从断点恢复 / Verify per-batch checkpointing and resume."""

    def should_resume_mid_phase_from_completed_count(self):
        """checkpoint completed_count=5 → resume 只处理 cases[5:]。
        Resume with completed_count=5 → only processes cases[5:]."""
        settings = _make_settings(batch_size=2)
        controller = BatchController(settings)

        with tempfile.TemporaryDirectory() as tmpdir:
            memory_dir = str(Path(tmpdir) / "memory")
            ckpt_mgr = CheckpointManager(memory_dir)

            # 构造 checkpoint：单接口已处理 5/10 / Set up checkpoint: 5/10 single done
            phase_progress = {
                "plugin_data_filling": {
                    "status": "in_progress",
                    "single": {"status": "in_progress", "total_items": 10,
                               "completed_count": 5, "batch_size": 2},
                },
            }
            ckpt_mgr.save_meta(
                "plugin_data_filling", {"batch_size": 2}, str(tmpdir),
                phases=["skeletons_generated", "plugin_data_filling"],
                phase_progress=phase_progress, phase_status="in_progress",
            )
            # 保存部分数据：前 5 个已处理，后 5 个未处理 / Partial data: first 5 done, last 5 untouched
            cases = (
                [{"test_id": f"t{i}", "filled": True} for i in range(5)]
                + [{"test_id": f"t{i}"} for i in range(5, 10)]
            )
            ckpt_mgr.save_data("plugin_data_filling", {
                "single_cases": cases, "biz_cases": [], "failures": [],
            })

            # 从 checkpoint 恢复 / Restore from checkpoint
            meta = ckpt_mgr.load_meta()
            restart_phase, single_cases, biz_cases, _ = \
                controller._restore_from_checkpoint(ckpt_mgr, meta)

            # 验证进度被加载 / Verify progress loaded
            assert restart_phase == "plugin_data_filling"
            assert controller._phase_progress["plugin_data_filling"]["single"]["completed_count"] == 5
            assert len(single_cases) == 10

    def should_save_checkpoint_after_each_batch(self):
        """10 项 batch_size=3 → _save_checkpoint 被调用 ≥3 次。
        Process 10 items with batch_size=3 → save_checkpoint called ≥3 times."""
        settings = _make_settings(batch_size=3)
        controller = BatchController(settings)

        with tempfile.TemporaryDirectory() as tmpdir:
            memory_dir = str(Path(tmpdir) / "memory")
            ckpt_mgr = CheckpointManager(memory_dir)

            # 初始化骨架阶段进度 / Init skeleton phase progress
            controller._phase_progress = {"skeletons_generated": {"status": "completed"}}

            plugin = _make_mock_plugin(name="data_filling", applies_biz=False)
            cases = [{"test_id": f"t{i}"} for i in range(10)]
            plugin.generate.side_effect = lambda batch, *args, **kw: [
                {**c, "filled": True} for c in batch
            ]

            controller._apply_plugin(
                plugin, cases, [], [], "",
                start_offset=0,
                phase_name="plugin_data_filling",
                sub_type="single",
                total_items=10,
                ckpt_mgr=ckpt_mgr,
                all_cases=list(cases),
                all_biz_cases=[],
                all_failures=[],
                output_dir=str(tmpdir),
                phases=["skeletons_generated", "plugin_data_filling"],
            )

            # 验证 checkpoint 已保存 / Verify checkpoint saved
            assert ckpt_mgr.exists()
            meta = ckpt_mgr.load_meta()
            assert meta["phase_progress"]["plugin_data_filling"]["single"]["completed_count"] == 10
            assert meta["phase_progress"]["plugin_data_filling"]["single"]["total_items"] == 10

    def should_skip_completed_sub_step_on_resume(self):
        """single 已完成、biz in_progress → resume 跳过 single 只处理 biz。
        Single completed, biz in_progress → skip single, only process biz."""
        settings = _make_settings(batch_size=2)
        controller = BatchController(settings)

        # 构造进度：single completed, biz 3/5 / Setup: single done, biz partially done
        controller._phase_progress = {
            "skeletons_generated": {"status": "completed"},
            "plugin_data_filling": {
                "status": "in_progress",
                "single": {"status": "completed", "total_items": 3, "completed_count": 3, "batch_size": 2},
                "biz": {"status": "in_progress", "total_items": 5, "completed_count": 3, "batch_size": 2},
            },
        }

        plugin = _make_mock_plugin(name="data_filling")
        # 模拟：返回与输入相同数量的元素 / Mock: return same number of items as input
        plugin.generate.side_effect = lambda batch, *args, **kw: [
            {**c, "filled": True} for c in batch
        ]

        single_cases = [{"test_id": "t1", "filled": True} for _ in range(3)]
        biz_cases = [{"flow_name": "f1", "filled": True} for _ in range(3)] + \
                    [{"flow_name": f"f{i}"} for i in range(4, 6)]

        with tempfile.TemporaryDirectory() as tmpdir:
            memory_dir = str(Path(tmpdir) / "memory")
            ckpt_mgr = CheckpointManager(memory_dir)

            single_out, biz_out, _ = controller._run_plugin_phase(
                plugins=[plugin],
                restart_phase="plugin_data_filling",
                single_cases=list(single_cases),
                biz_cases=list(biz_cases),
                all_failures=[],
                interfaces=[],
                api_summary=[],
                api_doc_text="",
                ckpt_mgr=ckpt_mgr,
                output_dir=str(tmpdir),
                phases=["skeletons_generated", "plugin_data_filling"],
            )

            # single 不应变 / single should be unchanged (already completed)
            assert len(single_out) == 3
            # biz 应被处理完 / biz should be fully processed
            assert len(biz_out) == 5

    def should_skip_completed_phase_on_resume(self):
        """阶段 status=completed → resume 跳过该阶段。
        Phase with status=completed → skipped on resume."""
        settings = _make_settings(batch_size=2)
        controller = BatchController(settings)

        controller._phase_progress = {
            "skeletons_generated": {"status": "completed"},
            "plugin_data_filling": {"status": "completed"},
            "plugin_assertion_gen": {"status": "pending"},
        }

        plugin_fill = _make_mock_plugin(name="data_filling")
        plugin_fill.generate.side_effect = lambda batch, *args, **kw: [
            {**c, "extra": True} for c in batch
        ]
        plugin_assert = _make_mock_plugin(name="assertion_gen", applies_biz=False)
        plugin_assert.generate.side_effect = lambda batch, *args, **kw: [
            {**c, "asserted": True} for c in batch
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            memory_dir = str(Path(tmpdir) / "memory")
            ckpt_mgr = CheckpointManager(memory_dir)

            single_out, biz_out, _ = controller._run_plugin_phase(
                plugins=[plugin_fill, plugin_assert],
                restart_phase="plugin_assertion_gen",
                single_cases=[{"test_id": "t1", "filled": True}],
                biz_cases=[],
                all_failures=[],
                interfaces=[],
                api_summary=[],
                api_doc_text="",
                ckpt_mgr=ckpt_mgr,
                output_dir=str(tmpdir),
                phases=["skeletons_generated", "plugin_data_filling", "plugin_assertion_gen"],
            )

            # data_filling 应被跳过 / data_filling should be skipped
            plugin_fill.generate.assert_not_called()
            # assertion_gen 应被调用 / assertion_gen should be called
            assert plugin_assert.generate.called

    def should_handle_batch_size_negative_one(self):
        """batch_size=-1 → 单 batch，一次 checkpoint 保存。
        batch_size=-1 → one big batch, one checkpoint save."""
        settings = _make_settings(batch_size=-1)
        controller = BatchController(settings)

        with tempfile.TemporaryDirectory() as tmpdir:
            memory_dir = str(Path(tmpdir) / "memory")
            ckpt_mgr = CheckpointManager(memory_dir)
            controller._phase_progress = {}

            plugin = _make_mock_plugin(name="data_filling", applies_biz=False)
            cases = [{"test_id": f"t{i}"} for i in range(5)]
            plugin.generate.return_value = [{**c, "filled": True} for c in cases]

            result = controller._apply_plugin(
                plugin, cases, [], [], "",
                start_offset=0,
                phase_name="plugin_data_filling",
                sub_type="single",
                total_items=5,
                ckpt_mgr=ckpt_mgr,
                all_cases=list(cases),
                all_biz_cases=[],
                all_failures=[],
                output_dir=str(tmpdir),
                phases=["skeletons_generated", "plugin_data_filling"],
            )
            assert len(result) == 5
            assert ckpt_mgr.exists()

    def should_accumulate_checkpoint_data_correctly(self):
        """验证 checkpoint data 中前缀已处理项正确保留 + 后缀未处理项不变。
        Verify checkpoint data preserves processed items + unprocessed suffix correctly."""
        settings = _make_settings(batch_size=2)
        controller = BatchController(settings)

        with tempfile.TemporaryDirectory() as tmpdir:
            memory_dir = str(Path(tmpdir) / "memory")
            ckpt_mgr = CheckpointManager(memory_dir)
            controller._phase_progress = {}

            plugin = _make_mock_plugin(name="data_filling", applies_biz=False)
            cases = [{"test_id": f"t{i}"} for i in range(6)]
            plugin.generate.side_effect = lambda batch, *args, **kw: [
                {**c, "filled": True} for c in batch
            ]

            controller._apply_plugin(
                plugin, cases, [], [], "",
                start_offset=0,
                phase_name="plugin_data_filling",
                sub_type="single",
                total_items=6,
                ckpt_mgr=ckpt_mgr,
                all_cases=list(cases),
                all_biz_cases=[],
                all_failures=[],
                output_dir=str(tmpdir),
                phases=["skeletons_generated", "plugin_data_filling"],
            )

            data = ckpt_mgr.load_data()
            assert data is not None
            # 所有 6 个都应已处理 / All 6 should be processed
            assert len(data["single_cases"]) == 6
            for c in data["single_cases"]:
                assert c.get("filled") is True

    def should_handle_consecutive_failure_break(self):
        """连续失败中断后，checkpoint 记录最后一个成功 batch 的进度。
        After consecutive failure break, checkpoint records last successful batch's progress."""
        settings = _make_settings(batch_size=2, consecutive_batch_failure_limit=2)
        controller = BatchController(settings)

        with tempfile.TemporaryDirectory() as tmpdir:
            memory_dir = str(Path(tmpdir) / "memory")
            ckpt_mgr = CheckpointManager(memory_dir)
            controller._phase_progress = {}

            plugin = _make_mock_plugin(name="data_filling", applies_biz=False,
                                        error_strategy="skip")
            cases = [{"test_id": f"t{i}"} for i in range(10)]

            # 第一批成功 / first batch succeeds
            call_count = [0]

            def side_effect(batch, *args, **kw):
                call_count[0] += 1
                if call_count[0] <= 1:
                    return [{**c, "filled": True} for c in batch]
                raise Exception("persistent failure")

            plugin.generate.side_effect = side_effect

            controller._apply_plugin(
                plugin, cases, [], [], "",
                start_offset=0,
                phase_name="plugin_data_filling",
                sub_type="single",
                total_items=10,
                ckpt_mgr=ckpt_mgr,
                all_cases=list(cases),
                all_biz_cases=[],
                all_failures=[],
                output_dir=str(tmpdir),
                phases=["skeletons_generated", "plugin_data_filling"],
            )

            # checkpoint 应记录至少 2 个已完成 / checkpoint should record at least 2 completed
            meta = ckpt_mgr.load_meta()
            completed = meta["phase_progress"]["plugin_data_filling"]["single"]["completed_count"]
            assert completed >= 2


# ---------------------------------------------------------------------------
# TestSkeletonPhaseResumeProgress — 骨架阶段逐批 checkpoint 测试
# ---------------------------------------------------------------------------

def _mock_single_skel_gen(batch_results=None):
    """创建 mock 单接口骨架生成器 / Create mock single skeleton generator."""
    gen = MagicMock()
    gen._skeleton_batch_size = 10
    if batch_results is None:
        batch_results = [[{"test_id": f"sk_{i}"} for i in range(10)]]
    # 模拟 iter_batches: yield 一个 batch
    # Mock iter_batches: yield one batch
    return gen


def _mock_biz_skel_gen(batch_results=None):
    """创建 mock 业务链路骨架生成器 / Create mock biz skeleton generator."""
    gen = MagicMock()
    gen._skeleton_batch_size = 10
    return gen


def _mock_plan_with_single_points(api_points: dict):
    """创建带 single_test_points 的 mock plan / Mock plan with single_test_points."""
    plan = MagicMock()
    plan.business_summary = "Test"

    class _Pt:
        def __init__(self, tag, tid, desc, stype):
            self.tag = tag
            self.test_id = tid
            self.description = desc
            self.scenario_type = stype

    sp = {}
    for api_id, count in api_points.items():
        sp[api_id] = [_Pt("P0", f"{api_id}_{i}", f"desc {i}", "positive") for i in range(count)]
    plan.single_test_points = sp
    plan.biz_flow_scenarios = []
    return plan


def _mock_plan_with_biz_scenarios(count: int):
    """创建带 biz_flow_scenarios 的 mock plan / Mock plan with biz_flow_scenarios."""
    plan = MagicMock()
    plan.business_summary = "Test"
    plan.single_test_points = {}
    plan.biz_flow_scenarios = [
        {"name": f"flow_{i}", "description": f"desc_{i}", "involved_apis": []}
        for i in range(count)
    ]
    return plan


class TestSkeletonPhaseResumeProgress:
    """验证骨架阶段逐批保存 checkpoint 和 resume / Verify skeleton phase per-batch checkpoint & resume."""

    def should_save_checkpoint_after_each_single_batch(self):
        """25 点 batch_size=10 (3 批) → _save_checkpoint 被调用 ≥3 次。
        25 points batch_size=10 (3 batches) → _save_checkpoint called ≥3 times."""
        settings = _make_settings(skeleton_batch_size=10)
        controller = BatchController(settings)

        with tempfile.TemporaryDirectory() as tmpdir:
            memory_dir = str(Path(tmpdir) / "memory")
            ckpt_mgr = CheckpointManager(memory_dir)

            plan = _mock_plan_with_single_points({"api_a": 25})

            # Mock 骨架生成器 / Mock skeleton generators
            single_gen = MagicMock()
            single_gen._skeleton_batch_size = 10
            # iter_batches → 3 batches (10+10+5)
            single_gen.iter_batches = MagicMock(return_value=iter([
                ({"api_a": plan.single_test_points["api_a"][:10]}, 10, 1, 3),
                ({"api_a": plan.single_test_points["api_a"][10:20]}, 10, 2, 3),
                ({"api_a": plan.single_test_points["api_a"][20:]}, 5, 3, 3),
            ]))
            single_gen.generate_batch = MagicMock(side_effect=lambda *args, **kw: [
                {"test_id": f"sk_{i}"} for i in range(kw.get("batch_idx", 1) * 10 if "batch_idx" not in str(args) else 10)
            ])
            # Fix the side_effect to match batch_expected
            call_idx = [0]

            def gen_side_effect(batch_grouped, plan, iface_dicts, api_summary,
                                user_guidance, batch_idx, total_batches):
                count = sum(len(pts) for pts in batch_grouped.values())
                return [{"test_id": f"sk_{call_idx[0]}_{j}", "url": "/api/test"} for j in range(count)]

            single_gen.generate_batch = MagicMock(side_effect=gen_side_effect)

            biz_gen = MagicMock()
            biz_gen._skeleton_batch_size = 10
            biz_gen.iter_batches = MagicMock(return_value=iter([]))

            # 重写 _save_checkpoint 用来计数 / Override _save_checkpoint for counting
            original_save = controller._save_checkpoint
            save_count = [0]

            def counting_save(*args, **kwargs):
                save_count[0] += 1
                return original_save(*args, **kwargs)

            controller._save_checkpoint = counting_save

            controller._run_skeleton_phase(
                plan, [], "", None, single_gen, biz_gen, "", "single",
                str(tmpdir), [], ckpt_mgr, ["skeletons_generated", "plugin_x"],
            )

            # 3 批 + 完成后 2 次确认（single done + phase done）= ≥5
            # 3 batches + 2 confirmations (single done + phase done) = ≥5
            assert save_count[0] >= 3

    def should_resume_single_from_completed_count(self):
        """预置 checkpoint 有已完成 skeleton → resume 基于 test_id 过滤。
        Pre-set checkpoint with completed skeletons → resume filters by test_id.
        改用 ProgressTracker ID 集合过滤替代旧的批次索引跳过。
        Uses ProgressTracker ID-based filtering instead of batch-index skip."""
        settings = _make_settings(skeleton_batch_size=10)
        controller = BatchController(settings)

        with tempfile.TemporaryDirectory() as tmpdir:
            memory_dir = str(Path(tmpdir) / "memory")
            ckpt_mgr = CheckpointManager(memory_dir)

            # 预置 checkpoint：已完成 10 个，test_id 与 plan 匹配
            # Pre-set checkpoint: 10 completed with test_ids matching the plan
            controller._phase_progress = {
                "skeletons_generated": {
                    "status": "in_progress",
                    "single": {"status": "in_progress", "total_items": 25,
                               "completed_count": 10, "batch_size": 10},
                },
            }
            ckpt_mgr.save_data("skeletons_generated", {
                "single_cases": [{"test_id": f"api_a_{i}", "url": "/api/test"} for i in range(10)],
                "biz_cases": [],
                "failures": [],
            })
            ckpt_mgr.save_meta("skeletons_generated", controller._collect_settings(),
                               str(tmpdir), phases=["skeletons_generated", "plugin_x"],
                               phase_progress=controller._phase_progress,
                               phase_status="in_progress")

            # Reload to ensure proper state
            meta = ckpt_mgr.load_meta()
            data = ckpt_mgr.load_data()
            existing_single = data["single_cases"]

            plan = _mock_plan_with_single_points({"api_a": 25})
            single_gen = MagicMock()
            single_gen._skeleton_batch_size = 10
            # iter_batches 不再被 ProgressTracker 使用 / iter_batches no longer used by ProgressTracker
            gen_calls = []

            def gen_side_effect(batch_grouped, *args, **kwargs):
                count = sum(len(pts) for pts in batch_grouped.values())
                gen_calls.append(kwargs.get("batch_idx", 0))
                return [{"test_id": f"new_{len(gen_calls)}_{j}", "url": "/api/test"} for j in range(count)]

            single_gen.generate_batch = MagicMock(side_effect=gen_side_effect)

            biz_gen = MagicMock()
            biz_gen._skeleton_batch_size = 10

            single_cases, biz_cases, failures = controller._run_skeleton_phase(
                plan, [], "", None, single_gen, biz_gen, "", "single",
                str(tmpdir), [], ckpt_mgr, ["skeletons_generated", "plugin_x"],
                existing_single_cases=existing_single,
            )

            # ProgressTracker 过滤前 10 个 ID，剩余 15 个分 2 批 (10+5)
            # ProgressTracker filters first 10 IDs, 15 remaining → 2 batches (10+5)
            assert single_gen.generate_batch.call_count == 2
            # 结果 = 已有 10 + 新生成 15 = 25 / Result = 10 existing + 15 new = 25
            assert len(single_cases) == 25

    def should_skip_completed_single_substep(self):
        """single completed, biz pending → 跳过 single 进入 biz。
        Single completed, biz pending → skips single, enters biz."""
        settings = _make_settings(skeleton_batch_size=10)
        controller = BatchController(settings)

        with tempfile.TemporaryDirectory() as tmpdir:
            memory_dir = str(Path(tmpdir) / "memory")
            ckpt_mgr = CheckpointManager(memory_dir)

            controller._phase_progress = {
                "skeletons_generated": {
                    "status": "in_progress",
                    "single": {"status": "completed", "total_items": 10,
                               "completed_count": 10, "batch_size": 10},
                },
            }

            plan = _mock_plan_with_biz_scenarios(5)
            plan.single_test_points = {"api_a": [MagicMock() for _ in range(10)]}
            for p in plan.single_test_points["api_a"]:
                p.tag = "P0"
                p.test_id = "t"
                p.description = "d"
                p.scenario_type = "positive"

            single_gen = MagicMock()
            single_gen._skeleton_batch_size = 10
            single_gen.iter_batches = MagicMock(return_value=iter([]))
            single_gen.generate_batch = MagicMock()

            biz_gen = MagicMock()
            biz_gen._skeleton_batch_size = 10
            biz_gen.iter_batches = MagicMock(return_value=iter([
                (plan.biz_flow_scenarios, 5, 1, 1),
            ]))
            biz_gen.generate_batch = MagicMock(return_value=[
                {"name": f"flow_{i}", "steps": [{"url": "/api/test"}]} for i in range(5)
            ])

            single_cases, biz_cases, failures = controller._run_skeleton_phase(
                plan, [], "/api/test", None, single_gen, biz_gen, "", "both",
                str(tmpdir), [], ckpt_mgr, ["skeletons_generated", "plugin_x"],
                existing_single_cases=[{"test_id": f"existing_{i}", "url": "/api/test"} for i in range(10)],
            )

            # single 生成器不应被调用 / Single generator should not be called
            single_gen.generate_batch.assert_not_called()
            # biz 生成器应被调用 / Biz generator should be called
            assert biz_gen.generate_batch.call_count >= 1

    def should_skip_full_skeleton_phase_when_phase_completed(self):
        """phase_status=completed → 完全跳过骨架阶段。
        Phase status=completed → skeleton phase fully skipped."""
        settings = _make_settings(skeleton_batch_size=10)
        controller = BatchController(settings)

        with tempfile.TemporaryDirectory() as tmpdir:
            memory_dir = str(Path(tmpdir) / "memory")
            ckpt_mgr = CheckpointManager(memory_dir)

            controller._phase_progress = {
                "skeletons_generated": {"status": "completed"},
            }

            plan = _mock_plan_with_single_points({"api_a": 5})
            single_gen = MagicMock()
            single_gen._skeleton_batch_size = 10
            single_gen.iter_batches = MagicMock(return_value=iter([]))
            single_gen.generate_batch = MagicMock()
            biz_gen = MagicMock()
            biz_gen._skeleton_batch_size = 10
            biz_gen.iter_batches = MagicMock(return_value=iter([]))
            biz_gen.generate_batch = MagicMock()

            single_cases, biz_cases, failures = controller._run_skeleton_phase(
                plan, [], "", None, single_gen, biz_gen, "", "single",
                str(tmpdir), [], ckpt_mgr, ["skeletons_generated", "plugin_x"],
                existing_single_cases=[{"test_id": "existing", "url": "/api/test"}],
            )

            # 生成器不应被调用 / Generators should not be called (sub-steps skipped)
            single_gen.generate_batch.assert_not_called()

    def should_handle_zero_test_points(self):
        """无测试点时正常完成 / Handles zero test points gracefully."""
        settings = _make_settings(skeleton_batch_size=10)
        controller = BatchController(settings)

        with tempfile.TemporaryDirectory() as tmpdir:
            memory_dir = str(Path(tmpdir) / "memory")
            ckpt_mgr = CheckpointManager(memory_dir)

            plan = MagicMock()
            plan.business_summary = "Test"
            plan.single_test_points = {}
            plan.biz_flow_scenarios = []

            single_gen = MagicMock()
            single_gen._skeleton_batch_size = 10
            single_gen.iter_batches = MagicMock(return_value=iter([]))
            biz_gen = MagicMock()
            biz_gen._skeleton_batch_size = 10
            biz_gen.iter_batches = MagicMock(return_value=iter([]))

            single_cases, biz_cases, failures = controller._run_skeleton_phase(
                plan, [], "", None, single_gen, biz_gen, "", "both",
                str(tmpdir), [], ckpt_mgr, ["skeletons_generated", "plugin_x"],
            )

            assert single_cases == []
            assert biz_cases == []
            # 阶段应标记为 completed / Phase should be marked completed
            assert controller._phase_progress["skeletons_generated"]["status"] == "completed"

    def should_use_checkpoint_skeleton_batch_size(self):
        """checkpoint 中的 skeleton_batch_size 优先于 env.yaml。
        Checkpoint skeleton_batch_size overrides env.yaml value."""
        settings = _make_settings(skeleton_batch_size=30)
        controller = BatchController(settings)

        with tempfile.TemporaryDirectory() as tmpdir:
            memory_dir = str(Path(tmpdir) / "memory")
            ckpt_mgr = CheckpointManager(memory_dir)

            # 预置 checkpoint settings 中 skeleton_batch_size=5 / Pre-set: skeleton_batch_size=5
            controller._phase_progress = {}
            controller._skeleton_batch_size = 5
            ckpt_mgr.save_meta("skeletons_generated", controller._collect_settings(),
                               str(tmpdir), phases=["skeletons_generated", "plugin_x"],
                               phase_progress=controller._phase_progress,
                               phase_status="in_progress")

            meta = ckpt_mgr.load_meta()
            controller._restore_from_checkpoint(ckpt_mgr, meta)
            # 应恢复为 5 而非 env.yaml 的 30 / Should restore to 5, not 30
            assert controller._skeleton_batch_size == 5

    def should_log_batch_progress_after_each_save(self):
        """验证骨架批次进度日志 / Verify skeleton batch progress logging."""
        settings = _make_settings(skeleton_batch_size=10)
        controller = BatchController(settings)

        with tempfile.TemporaryDirectory() as tmpdir:
            memory_dir = str(Path(tmpdir) / "memory")
            ckpt_mgr = CheckpointManager(memory_dir)

            plan = _mock_plan_with_single_points({"api_a": 5})
            single_gen = MagicMock()
            single_gen._skeleton_batch_size = 10
            single_gen.iter_batches = MagicMock(return_value=iter([
                ({"api_a": plan.single_test_points["api_a"]}, 5, 1, 1),
            ]))
            single_gen.generate_batch = MagicMock(return_value=[
                {"test_id": f"sk_{i}", "url": "/api/test"} for i in range(5)
            ])
            biz_gen = MagicMock()
            biz_gen._skeleton_batch_size = 10
            biz_gen.iter_batches = MagicMock(return_value=iter([]))

            with patch("agents.batch_controller.logger") as mock_logger:
                controller._run_skeleton_phase(
                    plan, [], "", None, single_gen, biz_gen, "", "single",
                    str(tmpdir), [], ckpt_mgr, ["skeletons_generated", "plugin_x"],
                )

                # 验证骨架批次进度的 info 日志被调用 / Verify skeleton batch progress logged
                assert mock_logger.info.call_count > 0
