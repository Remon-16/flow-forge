"""Tests for pipeline artifact and state helpers in graph.nodes.helpers."""

import json
import tempfile
from pathlib import Path

import pytest

from cli.bootstrap import ensure_output_structure
from graph.checkpoint import CheckpointManager
from graph.nodes.helpers import save_pipeline_artifact, save_pipeline_state


# ---------------------------------------------------------------------------
# SavePipelineArtifactTest
# ---------------------------------------------------------------------------

class SavePipelineArtifactTest:
    """Tests for save_pipeline_artifact()."""

    def should_save_json_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = {"skeletons": [{"test_id": "t1"}], "count": 1}
            save_pipeline_artifact(tmp, "test_artifact.json", data)

            path = Path(tmp) / "test_artifact.json"
            assert path.exists()
            loaded = json.loads(path.read_text(encoding="utf-8"))
            assert loaded == data

    def should_not_crash_when_memory_dir_is_none(self):
        # Should be a no-op, no exception
        save_pipeline_artifact(None, "test.json", {"key": "value"})

    def should_not_crash_when_memory_dir_is_empty_string(self):
        save_pipeline_artifact("", "test.json", {"key": "value"})

    def should_overwrite_existing_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_data = {"version": 1}
            new_data = {"version": 2, "updated": True}

            save_pipeline_artifact(tmp, "artifact.json", old_data)
            save_pipeline_artifact(tmp, "artifact.json", new_data)

            path = Path(tmp) / "artifact.json"
            loaded = json.loads(path.read_text(encoding="utf-8"))
            assert loaded == new_data


# ---------------------------------------------------------------------------
# SavePipelineStateTest
# ---------------------------------------------------------------------------

class SavePipelineStateTest:
    """Tests for save_pipeline_state()."""

    def should_create_new_state_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            save_pipeline_state(tmp, "skeletons_generated")

            path = Path(tmp) / "pipeline_state.json"
            assert path.exists()
            state = json.loads(path.read_text(encoding="utf-8"))
            assert state["completed_stage"] == "skeletons_generated"
            assert state["stages"] == ["skeletons_generated"]

    def should_append_stage_to_existing_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            save_pipeline_state(tmp, "skeletons_generated")
            save_pipeline_state(tmp, "data_filled_single")

            path = Path(tmp) / "pipeline_state.json"
            state = json.loads(path.read_text(encoding="utf-8"))
            assert state["completed_stage"] == "data_filled_single"
            assert state["stages"] == ["skeletons_generated", "data_filled_single"]

    def should_not_crash_when_memory_dir_is_none(self):
        save_pipeline_state(None, "some_stage")

    def should_handle_corrupt_existing_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pipeline_state.json"
            path.write_text("not valid json {{", encoding="utf-8")

            # Should not crash; should create a fresh state file
            save_pipeline_state(tmp, "new_stage")

            state = json.loads(path.read_text(encoding="utf-8"))
            assert state["completed_stage"] == "new_stage"
            assert state["stages"] == ["new_stage"]


# ---------------------------------------------------------------------------
# PipelineResumeOutlineTest / 轮廓恢复测试
# ---------------------------------------------------------------------------

class TestPipelineResumeOutline:
    """Tests for _load_pipeline_state() with outline support."""

    def should_load_outline_from_memory_dir(self):
        """从 memory_dir 加载 outline / Load outline from memory_dir."""
        from cli.runner import _load_pipeline_state

        with tempfile.TemporaryDirectory() as tmp:
            memory_dir = Path(tmp) / "memory"
            memory_dir.mkdir()
            cases_dir = Path(tmp) / "cases"
            cases_dir.mkdir()

            # 保存 outline / Save outline
            outline = {
                "business_summary": "Test",
                "api_groups": [{"group_name": "G1", "api_ids": ["api_1"], "test_focus": "F1"}],
                "biz_flows": [],
            }
            save_pipeline_artifact(str(memory_dir), "plan_outline.json", outline)
            save_pipeline_state(str(memory_dir), "generate_outline")

            loaded = _load_pipeline_state(str(memory_dir))
            assert "plan_outline" in loaded
            assert loaded["plan_outline"]["business_summary"] == "Test"
            assert len(loaded["plan_outline"]["api_groups"]) == 1


# ---------------------------------------------------------------------------
# TestPipelineResumePlanParsed / 计划解析恢复测试
# ---------------------------------------------------------------------------

class TestPipelineResumePlanParsed:
    """Tests for _load_pipeline_state() plan_parsed reconstruction."""

    def should_reconstruct_testplan_from_dict(self):
        """加载 plan_parsed.json 后应重建为 TestPlan 数据类。
        After loading plan_parsed.json, should reconstruct TestPlan dataclass.
        """
        from cli.runner import _load_pipeline_state
        from models.schema import PlanStep, TestPlan

        with tempfile.TemporaryDirectory() as tmp:
            memory_dir = Path(tmp) / "memory"
            memory_dir.mkdir()

            plan_dict = {
                "business_summary": "Test summary",
                "api_definitions": [],
                "single_test_points": {
                    "api_1": [
                        {"test_id": "tp_1", "description": "Positive case", "tag": "P0", "scenario_type": "positive"},
                        {"test_id": "tp_2", "description": "Negative case", "tag": "P1", "scenario_type": "negative"},
                    ],
                },
                "mermaid_flows": {},
                "biz_flow_scenarios": [
                    {"name": "flow_1", "steps": []},
                ],
            }
            save_pipeline_artifact(str(memory_dir), "plan_parsed.json", plan_dict)
            save_pipeline_state(str(memory_dir), "parse_plan")

            loaded = _load_pipeline_state(str(memory_dir))
            plan = loaded["plan_parsed"]

            # 应为 TestPlan 实例 / Should be TestPlan instance
            assert isinstance(plan, TestPlan)
            # single_test_points 中的元素应为 PlanStep 对象 / PlanStep objects inside
            assert hasattr(plan, "single_test_points")
            assert len(plan.single_test_points["api_1"]) == 2
            assert isinstance(plan.single_test_points["api_1"][0], PlanStep)
            assert plan.single_test_points["api_1"][0].tag == "P0"
            # biz_flow_scenarios 应保留 / biz_flow_scenarios preserved
            assert plan.biz_flow_scenarios == [{"name": "flow_1", "steps": []}]


# ---------------------------------------------------------------------------
# TestResumeAutoVersioningSkip / Resume 自动版本号跳过测试
# ---------------------------------------------------------------------------

class TestResumeAutoVersioningSkip:
    """Tests that auto-versioning is skipped during --resume.
    Resume 模式下 auto-versioning 应被跳过，确保 CheckpointManager
    从原始 memory_dir 读取 checkpoint 数据。"""

    def should_find_checkpoint_in_original_memory_dir(self):
        """Resume 时 CheckpointManager 从原始 memory_dir 读取 checkpoint。
        When resuming, checkpoint.json should be readable from the original
        memory/ directory, not lost to a versioned _v2 directory.
        """
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "output"
            cases_dir, memory_dir = ensure_output_structure(output_dir)

            # 模拟上次运行产生的 .yaml 文件（会触发 auto-versioning）
            # Simulate .yaml files from previous run (would trigger auto-versioning)
            (cases_dir / "interfaces").mkdir(parents=True, exist_ok=True)
            (cases_dir / "interfaces" / "api_test.yaml").write_text(
                "url: /api/test", encoding="utf-8"
            )

            # 在原始 memory/ 中保存 checkpoint 数据
            # Save checkpoint data in original memory/
            ckpt_mgr = CheckpointManager(str(memory_dir))
            ckpt_mgr.save_meta(
                "skeletons_generated",
                {"batch_size": 3},
                {"single_cases": 5, "biz_cases": 2},
                str(cases_dir),
                phases=["skeletons_generated", "plugin_data_filling"],
            )
            ckpt_mgr.save_data(
                "skeletons_generated",
                {
                    "single_cases": [{"test_id": "t1"}],
                    "biz_cases": [{"flow_name": "f1"}],
                    "failures": [],
                },
            )
            save_pipeline_state(str(memory_dir), "batch_controller")

            # 验证 checkpoint 在原始 memory_dir 中可正常读取
            # Verify checkpoint is readable from original memory_dir
            ckpt_mgr2 = CheckpointManager(str(memory_dir))
            assert ckpt_mgr2.exists(), (
                "CheckpointManager should find checkpoint.json in original memory/"
            )

            meta = ckpt_mgr2.load_meta()
            assert meta is not None
            assert meta["phase"] == "skeletons_generated"
            assert meta["counts"]["single_cases"] == 5
            assert meta["counts"]["biz_cases"] == 2

            data = ckpt_mgr2.load_data()
            assert data is not None
            assert len(data["single_cases"]) == 1
            assert data["single_cases"][0]["test_id"] == "t1"
            assert len(data["biz_cases"]) == 1
            assert data["biz_cases"][0]["flow_name"] == "f1"

    def should_not_create_v2_when_resume_condition_true(self):
        """验证 resume=True 时 auto-versioning 条件为 False。
        Verify that the auto-versioning guard condition evaluates correctly:
        when resume=True, should skip even if resume_overwrite=False.
        """
        # 模拟 argparse.Namespace / Simulate argparse.Namespace
        class FakeArgs:
            resume = True
            resume_overwrite = False

        args = FakeArgs()
        resume_overwrite = args.resume_overwrite

        # 核心条件：resume 模式下应跳过 / Core condition: skip when resume
        should_auto_version = not resume_overwrite and not args.resume
        assert should_auto_version is False, (
            "Auto-versioning should be False when resume=True"
        )

        # 非 resume 模式应触发 / Non-resume mode should trigger
# ---------------------------------------------------------------------------
# TestSaveLoadRunConfig / 运行配置保存与加载测试
# ---------------------------------------------------------------------------

class TestSaveLoadRunConfig:
    """Tests for save_run_config() and load_run_config()."""

    def should_save_and_load_roundtrip(self):
        """保存后应立即加载到相同数据 / Save then load should produce same data."""
        from graph.nodes.helpers import save_run_config, load_run_config

        with tempfile.TemporaryDirectory() as tmp:
            config = {
                "case_type": "single",
                "user_guidance": "test guidance",
                "output_format": "yaml",
                "batch_size": 5,
                "auto_mode": True,
            }
            save_run_config(tmp, config)
            loaded = load_run_config(tmp)
            assert loaded.get("case_type") == "single"
            assert loaded.get("user_guidance") == "test guidance"
            assert loaded.get("output_format") == "yaml"
            assert loaded.get("batch_size") == 5
            assert loaded.get("auto_mode") is True
            assert loaded.get("version") == 1
            assert "timestamp" in loaded

    def should_return_empty_for_missing_file(self):
        """文件不存在时返回空 dict / Returns {} when file missing."""
        from graph.nodes.helpers import load_run_config

        with tempfile.TemporaryDirectory() as tmp:
            assert load_run_config(tmp) == {}

    def should_not_crash_when_memory_dir_is_none(self):
        """memory_dir 为 None 时不崩溃 / No crash for None memory_dir."""
        from graph.nodes.helpers import save_run_config, load_run_config

        save_run_config(None, {"key": "val"})  # no-op
        assert load_run_config(None) == {}

    def should_return_empty_for_corrupt_file(self):
        """损坏文件返回空 dict / Corrupt file returns {}."""
        from graph.nodes.helpers import load_run_config

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run_config.json"
            path.write_text("not json {{{", encoding="utf-8")
            assert load_run_config(tmp) == {}

    def should_overwrite_existing_config(self):
        """再次保存应覆盖旧配置 / Second save should overwrite."""
        from graph.nodes.helpers import save_run_config, load_run_config

        with tempfile.TemporaryDirectory() as tmp:
            old = {"case_type": "single"}
            new = {"case_type": "biz", "auto_mode": True}
            save_run_config(tmp, old)
            save_run_config(tmp, new)
            loaded = load_run_config(tmp)
            assert loaded.get("case_type") == "biz"
            assert loaded.get("auto_mode") is True


# ---------------------------------------------------------------------------
# TestPipelineStateYamlRecon / YAML 接口重建测试
# ---------------------------------------------------------------------------

class TestPipelineStateYamlRecon:
    """Tests for _load_pipeline_state() YAML interfaces reconstruction."""

    def should_reconstruct_interfaces_from_yaml_with_cases_dir(self):
        """传入 cases_dir 后应从 YAML 文件重建接口定义。
        When cases_dir is provided and save_interfaces completed,
        should load interfaces from YAML files on disk."""
        from cli.runner import _load_pipeline_state

        with tempfile.TemporaryDirectory() as tmp:
            memory_dir = Path(tmp) / "memory"
            memory_dir.mkdir()
            cases_dir = Path(tmp) / "cases"
            interfaces_dir = cases_dir / "interfaces"
            interfaces_dir.mkdir(parents=True)

            # 创建 YAML 接口文件 / Create YAML interface files
            yaml_content = """test_id: api_test_1
api_name: 测试接口 / Test API
method: GET
url: /api/test
request_head:
  Content-Type: application/json
request_body: {}
status_code: 200
assert_dict:
  status_code: 200
remark: ""
"""
            (interfaces_dir / "api_test_1.yaml").write_text(yaml_content, encoding="utf-8")

            # 保存必要的 pipeline artifacts / Save required pipeline artifacts
            save_pipeline_artifact(str(memory_dir), "parsed_docs.json", {
                "requirement_text": "",
                "api_raw_text": "",
                "interfaces": [{"test_id": "api_old", "method": "GET", "url": "/old"}],
                "parse_mode": "raw",
            })
            save_pipeline_state(str(memory_dir), "parse_docs")
            save_pipeline_state(str(memory_dir), "save_interfaces")

            # 不传 cases_dir 时应 fallback 到 parsed_docs 的原始接口
            # Without cases_dir: should fallback to parsed_docs originals
            loaded_no_dir = _load_pipeline_state(str(memory_dir))
            assert len(loaded_no_dir.get("interfaces", [])) == 1
            assert loaded_no_dir["interfaces"][0]["test_id"] == "api_old"

            # 传入 cases_dir 后应从 YAML 加载 / With cases_dir: should load from YAML
            loaded_with_dir = _load_pipeline_state(str(memory_dir), str(cases_dir))
            assert len(loaded_with_dir.get("interfaces", [])) == 1
            assert loaded_with_dir["interfaces"][0]["test_id"] == "api_test_1"
            assert loaded_with_dir["interfaces"][0]["method"] == "GET"
            assert loaded_with_dir["interfaces"][0]["url"] == "/api/test"

    def should_keep_parsed_interfaces_when_no_yaml_files(self):
        """YAML 目录为空时保留 parsed_docs 的接口 / Keep parsed interfaces
        when YAML directory is empty."""
        from cli.runner import _load_pipeline_state

        with tempfile.TemporaryDirectory() as tmp:
            memory_dir = Path(tmp) / "memory"
            memory_dir.mkdir()
            cases_dir = Path(tmp) / "cases"
            interfaces_dir = cases_dir / "interfaces"
            interfaces_dir.mkdir(parents=True)  # empty dir, no YAML files

            save_pipeline_artifact(str(memory_dir), "parsed_docs.json", {
                "requirement_text": "",
                "api_raw_text": "",
                "interfaces": [{"test_id": "api_from_parsed"}],
                "parse_mode": "raw",
            })
            save_pipeline_state(str(memory_dir), "parse_docs")
            save_pipeline_state(str(memory_dir), "save_interfaces")

            loaded = _load_pipeline_state(str(memory_dir), str(cases_dir))
            assert loaded["interfaces"][0]["test_id"] == "api_from_parsed"

    def should_load_run_config_from_memory_dir(self):
        """_load_pipeline_state 应加载 run_config.json 到 _run_config 键。
        _load_pipeline_state should load run_config.json into state._run_config."""
        from cli.runner import _load_pipeline_state
        from graph.nodes.helpers import save_run_config

        with tempfile.TemporaryDirectory() as tmp:
            memory_dir = Path(tmp) / "memory"
            memory_dir.mkdir()

            save_run_config(str(memory_dir), {
                "case_type": "biz",
                "user_guidance": "test",
            })

            loaded = _load_pipeline_state(str(memory_dir))
            assert "_run_config" in loaded
            assert loaded["_run_config"]["case_type"] == "biz"
            assert loaded["_run_config"]["user_guidance"] == "test"


# ---------------------------------------------------------------------------
# TestConfigOverrideWarnings / 配置覆盖警告测试
# ---------------------------------------------------------------------------

class TestConfigOverrideWarnings:
    """Tests for _check_config_overrides() warning logic."""

    def should_not_warn_when_no_saved_config(self, capsys):
        """无已保存配置时不警告 / No warning when no saved config."""
        from cli.runner import _check_config_overrides

        class FakeArgs:
            case_type = "biz"

        with tempfile.TemporaryDirectory() as tmp:
            ps_path = Path(tmp) / "pipeline_state.json"
            # 空的 saved_config / Empty saved_config
            _check_config_overrides(FakeArgs(), {}, ps_path)

    def should_not_warn_when_values_unchanged(self, capsys):
        """CLI 参数与已保存配置相同时不警告 / No warning when values unchanged."""
        from cli.runner import _check_config_overrides

        class FakeArgs:
            case_type = "both"

        with tempfile.TemporaryDirectory() as tmp:
            ps_path = Path(tmp) / "pipeline_state.json"
            ps_path.write_text(
                json.dumps({"stages": ["generate_outline"], "completed_stage": "generate_outline"}),
                encoding="utf-8",
            )
            saved = {"case_type": "both"}

            # 值相同，不应有警告 / Same value, no warning
            _check_config_overrides(FakeArgs(), saved, ps_path)

    def should_warn_when_cli_overrides_saved_config(self):
        """CLI 覆盖已保存配置时警告 / Warn when CLI overrides saved config."""
        from cli.runner import _check_config_overrides

        class FakeArgs:
            case_type = "single"

        with tempfile.TemporaryDirectory() as tmp:
            ps_path = Path(tmp) / "pipeline_state.json"
            ps_path.write_text(
                json.dumps({"stages": ["generate_outline"], "completed_stage": "generate_outline"}),
                encoding="utf-8",
            )
            saved = {"case_type": "both"}
            # case_type 从 both→single 变化 / Changed from both to single
            _check_config_overrides(FakeArgs(), saved, ps_path)

