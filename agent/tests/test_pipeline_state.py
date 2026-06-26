"""Tests for pipeline artifact and state helpers in graph.nodes.helpers."""

import json
import tempfile
from pathlib import Path

import pytest

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
