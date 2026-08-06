"""Tests for CheckpointManager — checkpoint save / load / restart logic."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from graph.checkpoint import CheckpointManager, CURRENT_VERSION


# ---------------------------------------------------------------------------
# CheckpointManagerTest
# ---------------------------------------------------------------------------

class TestCheckpointManager:
    """Tests for CheckpointManager save, load, and existence operations."""

    def should_save_and_load_meta(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = CheckpointManager(tmp)
            settings = {"llm_model": "gpt-4o"}
            mgr.save_meta("data_filled_single", settings, "/output")

            meta = mgr.load_meta()
            assert meta is not None
            assert meta["version"] == CURRENT_VERSION
            assert meta["phase"] == "data_filled_single"
            assert meta["phase_status"] == "completed"
            assert meta["settings"] == settings
            assert meta["output_dir"] == "/output"
            assert "timestamp" in meta

    def should_save_and_load_meta_with_phases(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = CheckpointManager(tmp)
            custom_phases = ["phase_a", "phase_b", "phase_c"]
            mgr.save_meta(
                "phase_b", {}, "/out",
                phases=custom_phases,
            )

            meta = mgr.load_meta()
            assert meta is not None
            assert meta["phases"] == custom_phases

    def should_save_and_load_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = CheckpointManager(tmp)
            payload = {"single_cases": [{"test_id": "t1"}], "biz_flows": []}
            mgr.save_data("data_filled_single", payload)

            data = mgr.load_data()
            assert data is not None
            assert data["version"] == CURRENT_VERSION
            assert data["phase"] == "data_filled_single"
            assert data["single_cases"] == [{"test_id": "t1"}]
            assert data["biz_flows"] == []

    def should_return_none_for_missing_meta(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = CheckpointManager(tmp)
            assert mgr.load_meta() is None

    def should_return_none_for_corrupt_meta_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = CheckpointManager(tmp)
            mgr.meta_path.parent.mkdir(parents=True, exist_ok=True)
            mgr.meta_path.write_text("not valid json {{{", encoding="utf-8")

            assert mgr.load_meta() is None

    def should_return_none_for_version_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = CheckpointManager(tmp)
            mgr.meta_path.parent.mkdir(parents=True, exist_ok=True)
            mgr.meta_path.write_text(
                json.dumps({"version": 999, "phase": "x"}),
                encoding="utf-8",
            )

            assert mgr.load_meta() is None

    def should_return_none_for_corrupt_data_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = CheckpointManager(tmp)
            mgr.data_path.parent.mkdir(parents=True, exist_ok=True)
            mgr.data_path.write_text("garbage {{{{{{", encoding="utf-8")

            assert mgr.load_data() is None

    def should_return_false_when_checkpoint_does_not_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = CheckpointManager(tmp)
            assert mgr.exists() is False

    def should_handle_empty_phases_in_meta(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = CheckpointManager(tmp)
            mgr.save_meta("skeletons_generated", {}, "/out", phases=[])

            meta = mgr.load_meta()
            assert meta is not None
            assert meta["phases"] == []


# ---------------------------------------------------------------------------
# GetRestartPhaseTest
# ---------------------------------------------------------------------------

class TestGetRestartPhase:
    """Tests for CheckpointManager.get_restart_phase static method."""

    def should_return_next_phase_with_static_phases(self):
        # phases=None → uses default _PHASES
        meta = {"phase": "skeletons_generated", "phases": None}
        result = CheckpointManager.get_restart_phase(meta)
        assert result == "data_filled_single"

    def should_return_next_phase_with_dynamic_phases_from_meta(self):
        meta = {
            "phase": "stage2",
            "phases": ["stage1", "stage2", "stage3", "stage4"],
        }
        result = CheckpointManager.get_restart_phase(meta)
        assert result == "stage3"

    def should_fallback_to_first_phase_for_unknown_phase(self):
        meta = {"phase": "nonexistent_phase", "phases": None}
        result = CheckpointManager.get_restart_phase(meta)
        # Falls back to first phase in static _PHASES
        assert result == "skeletons_generated"

    def should_return_all_complete_when_last_phase(self):
        meta = {"phase": "plugins_applied", "phases": None}
        result = CheckpointManager.get_restart_phase(meta)
        assert result == "all_complete"

    def should_prefer_meta_phases_over_static(self):
        # meta has its own phases list → use it, not _PHASES
        meta = {
            "phase": "custom_step",
            "phases": ["custom_step", "another_step", "final_step"],
        }
        result = CheckpointManager.get_restart_phase(meta)
        assert result == "another_step"


# ---------------------------------------------------------------------------
# PhaseProgressTest / 阶段进度测试
# ---------------------------------------------------------------------------

class TestPhaseProgress:
    """Tests for phase_progress in save_meta / load_meta and get_restart_phase."""

    def should_return_current_phase_when_in_progress(self):
        """phase_status="in_progress" → 返回当前阶段，而非下一阶段。
        Returns current phase, not next phase, when in_progress."""
        meta = {
            "phase": "plugin_data_filling",
            "phase_status": "in_progress",
            "phases": ["skeletons_generated", "plugin_data_filling", "plugin_assertion"],
        }
        result = CheckpointManager.get_restart_phase(meta)
        assert result == "plugin_data_filling"

    def should_return_next_phase_when_completed(self):
        """phase_status="completed" → 返回下一阶段（原有行为）。
        Returns next phase when completed (existing behavior)."""
        meta = {
            "phase": "skeletons_generated",
            "phase_status": "completed",
            "phases": ["skeletons_generated", "plugin_data_filling", "plugin_assertion"],
        }
        result = CheckpointManager.get_restart_phase(meta)
        assert result == "plugin_data_filling"

    def should_save_and_load_phase_progress(self):
        """save_meta(phase_progress=...) → load_meta() 往返一致。
        phase_progress round-trips correctly through save/load."""
        with tempfile.TemporaryDirectory() as tmp:
            mgr = CheckpointManager(tmp)
            progress = {
                "skeletons_generated": {"status": "completed"},
                "plugin_data_filling": {
                    "status": "in_progress",
                    "single": {"status": "completed", "total_items": 100, "completed_count": 100, "batch_size": 10},
                    "biz": {"status": "in_progress", "total_items": 50, "completed_count": 35, "batch_size": 10},
                },
            }
            mgr.save_meta(
                "plugin_data_filling", {}, "/out",
                phases=["skeletons_generated", "plugin_data_filling", "plugin_assertion"],
                phase_progress=progress,
                phase_status="in_progress",
            )

            meta = mgr.load_meta()
            assert meta is not None
            assert meta["phase_status"] == "in_progress"
            assert "phase_progress" in meta
            loaded = meta["phase_progress"]
            assert loaded["skeletons_generated"]["status"] == "completed"
            assert loaded["plugin_data_filling"]["status"] == "in_progress"
            assert loaded["plugin_data_filling"]["single"]["completed_count"] == 100
            assert loaded["plugin_data_filling"]["biz"]["completed_count"] == 35

    def should_handle_missing_phase_progress_gracefully(self):
        """旧 checkpoint 无 phase_progress 字段 → load_meta() 正常返回，调用方自行 fallback。
        Old checkpoints without phase_progress load normally; caller handles fallback."""
        with tempfile.TemporaryDirectory() as tmp:
            mgr = CheckpointManager(tmp)
            mgr.save_meta("skeletons_generated", {}, "/out", phases=["skeletons_generated"])

            meta = mgr.load_meta()
            assert meta is not None
            # No phase_progress key — caller uses .get("phase_progress", {})
            assert "phase_progress" not in meta
            assert meta.get("phase_progress", {}) == {}
