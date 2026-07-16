"""Tests for feedback persistence — save/load/clear api_summary_feedback and plan_feedback.

反馈持久化测试 — api_summary_feedback 和 plan_feedback 的保存/加载/清除。
"""

import json
import tempfile
from pathlib import Path

import pytest

from graph.nodes.helpers import save_pipeline_artifact, save_pipeline_state


# ---------------------------------------------------------------------------
# TestApiFeedbackPersistence / API 分析反馈持久化
# ---------------------------------------------------------------------------


class TestApiFeedbackPersistence:
    """Tests for api_summary_feedback save/load/clear."""

    def should_save_feedback_on_interrupt(self):
        """interrupt 返回反馈时保存 api_analysis_feedback.json
        Should save api_analysis_feedback.json when interrupt returns feedback."""
        with tempfile.TemporaryDirectory() as tmp:
            memory_dir = Path(tmp) / "memory"
            memory_dir.mkdir()

            feedback = "请检查 /api/login 的认证方式"
            api_summary = [{"api_path": "/api/login", "method": "POST"}]

            # 模拟 analyze_api_node 保存 feedback
            save_pipeline_artifact(str(memory_dir), "api_analysis_feedback.json", {
                "feedback": feedback,
                "api_summary": api_summary,
            })

            fb_path = memory_dir / "api_analysis_feedback.json"
            assert fb_path.exists()
            loaded = json.loads(fb_path.read_text(encoding="utf-8"))
            assert loaded["feedback"] == feedback
            assert loaded["api_summary"] == api_summary

    def should_load_feedback_on_resume(self):
        """resume 时 _load_pipeline_state 恢复 api_summary_feedback
        _load_pipeline_state should restore api_summary_feedback from artifact."""
        from cli.runner import _load_pipeline_state

        with tempfile.TemporaryDirectory() as tmp:
            memory_dir = Path(tmp) / "memory"
            memory_dir.mkdir()

            # 保存 parsed_docs + api_summary + feedback
            save_pipeline_artifact(str(memory_dir), "parsed_docs.json", {
                "requirement_texts": [],
                "api_raw_text": "",
                "interfaces": [],
                "parse_mode": "raw",
            })
            save_pipeline_state(str(memory_dir), "parse_docs")

            save_pipeline_artifact(str(memory_dir), "api_summary.json", [
                {"api_path": "/api/login", "method": "POST"},
            ])
            save_pipeline_artifact(str(memory_dir), "api_analysis_feedback.json", {
                "feedback": "请检查认证方式 / Please check auth method",
                "api_summary": [{"api_path": "/api/login", "method": "POST", "notes": "可能需要 token / May need token"}],
            })
            save_pipeline_state(str(memory_dir), "analyze_api")

            loaded = _load_pipeline_state(str(memory_dir))
            assert "api_summary_feedback" in loaded
            assert loaded["api_summary_feedback"] == "请检查认证方式 / Please check auth method"
            # 有未处理 feedback 时 confirmed 应为 False
            assert loaded["api_summary_confirmed"] is False

    def should_set_confirmed_when_no_feedback(self):
        """无 feedback 文件时 confirmed 应为 True
        confirmed should be True when no feedback file exists."""
        from cli.runner import _load_pipeline_state

        with tempfile.TemporaryDirectory() as tmp:
            memory_dir = Path(tmp) / "memory"
            memory_dir.mkdir()

            save_pipeline_artifact(str(memory_dir), "parsed_docs.json", {
                "requirement_texts": [],
                "api_raw_text": "",
                "interfaces": [],
                "parse_mode": "raw",
            })
            save_pipeline_state(str(memory_dir), "parse_docs")

            save_pipeline_artifact(str(memory_dir), "api_summary.json", [
                {"api_path": "/api/test", "method": "GET"},
            ])
            save_pipeline_state(str(memory_dir), "analyze_api")

            loaded = _load_pipeline_state(str(memory_dir))
            assert loaded["api_summary_confirmed"] is True
            assert "api_summary_feedback" not in loaded

    def should_clear_feedback_after_consume(self):
        """feedback 被消费后应删除 artifact 文件
        Feedback artifact should be deleted after consumption."""
        with tempfile.TemporaryDirectory() as tmp:
            memory_dir = Path(tmp) / "memory"
            memory_dir.mkdir()

            # 先创建 feedback 文件
            save_pipeline_artifact(str(memory_dir), "api_analysis_feedback.json", {
                "feedback": "test feedback",
                "api_summary": [],
            })
            fb_path = memory_dir / "api_analysis_feedback.json"
            assert fb_path.exists()

            # 模拟 analyze_api_node 消费 feedback 后删除文件
            if fb_path.exists():
                fb_path.unlink()
            assert not fb_path.exists()


# ---------------------------------------------------------------------------
# TestPlanFeedbackPersistence / 计划审核反馈持久化
# ---------------------------------------------------------------------------


class TestPlanFeedbackPersistence:
    """Tests for plan_feedback save/load/clear."""

    def should_save_feedback_on_reject(self):
        """human_confirm reject 时保存 pending_feedback.json
        Should save pending_feedback.json when plan is rejected."""
        with tempfile.TemporaryDirectory() as tmp:
            memory_dir = Path(tmp) / "memory"
            memory_dir.mkdir()

            feedback = "请增加 API 错误码测试场景 / Add API error code test scenarios"
            plan_feedback_type = "text"
            plan_annotations = []

            # 模拟 human_confirm_node 保存 feedback
            save_pipeline_artifact(str(memory_dir), "pending_feedback.json", {
                "plan_feedback": feedback,
                "plan_feedback_type": plan_feedback_type,
                "plan_annotations": plan_annotations,
            })

            fb_path = memory_dir / "pending_feedback.json"
            assert fb_path.exists()
            loaded = json.loads(fb_path.read_text(encoding="utf-8"))
            assert loaded["plan_feedback"] == feedback
            assert loaded["plan_feedback_type"] == "text"

    def should_load_pending_feedback_on_resume(self):
        """resume 时 _load_pipeline_state 恢复 plan_feedback
        _load_pipeline_state should restore plan_feedback from artifact."""
        from cli.runner import _load_pipeline_state

        with tempfile.TemporaryDirectory() as tmp:
            memory_dir = Path(tmp) / "memory"
            memory_dir.mkdir()

            save_pipeline_artifact(str(memory_dir), "parsed_docs.json", {
                "requirement_texts": [],
                "api_raw_text": "",
                "interfaces": [],
                "parse_mode": "raw",
            })
            save_pipeline_state(str(memory_dir), "parse_docs")

            save_pipeline_artifact(str(memory_dir), "pending_feedback.json", {
                "plan_feedback": "增加边界测试 / Add boundary tests",
                "plan_feedback_type": "text",
                "plan_annotations": [],
            })

            loaded = _load_pipeline_state(str(memory_dir))
            assert loaded["plan_feedback"] == "增加边界测试 / Add boundary tests"
            assert loaded["plan_feedback_type"] == "text"
            # 有未处理 feedback 时 confirmed 应为 False
            assert loaded["plan_confirmed"] is False

    def should_clear_feedback_after_revision(self):
        """修订完成后应删除 pending_feedback.json
        pending_feedback.json should be deleted after revision completion."""
        with tempfile.TemporaryDirectory() as tmp:
            memory_dir = Path(tmp) / "memory"
            memory_dir.mkdir()

            # 先创建
            save_pipeline_artifact(str(memory_dir), "pending_feedback.json", {
                "plan_feedback": "test",
                "plan_feedback_type": "text",
                "plan_annotations": [],
            })
            fb_path = memory_dir / "pending_feedback.json"
            assert fb_path.exists()

            # 模拟 revise_plan_node 删除
            if fb_path.exists():
                fb_path.unlink()
            assert not fb_path.exists()


# ---------------------------------------------------------------------------
# TestResumeRoutingWithPendingFeedback / 有未处理反馈时的 resume 路由
# ---------------------------------------------------------------------------


class TestResumeRoutingWithPendingFeedback:
    """Tests that _route_resume detects pending feedback files."""

    def should_route_to_human_confirm_when_pending_feedback_exists(self):
        """pending_feedback.json 存在时路由到 human_confirm
        When pending_feedback.json exists, _route_resume should return 'human_confirm'."""
        from graph.workflow import _route_resume

        with tempfile.TemporaryDirectory() as tmp:
            memory_dir = Path(tmp) / "memory"
            memory_dir.mkdir()

            # 创建 pending_feedback.json（即使 pipeline_state 显示已到 batch_controller）
            save_pipeline_artifact(str(memory_dir), "pending_feedback.json", {
                "plan_feedback": "test",
                "plan_feedback_type": "text",
            })
            # 同时保存 pipeline_state（正常情况已到 write_output）
            save_pipeline_state(str(memory_dir), "write_output")

            state = {"memory_dir": str(memory_dir)}
            result = _route_resume(state)
            # 应优先路由到 human_confirm 而不是 write_output
            assert result == "human_confirm"

    def should_route_to_analyze_api_when_api_feedback_exists(self):
        """api_analysis_feedback.json 存在时路由到 analyze_api
        When api_analysis_feedback.json exists, route to 'analyze_api'."""
        from graph.workflow import _route_resume

        with tempfile.TemporaryDirectory() as tmp:
            memory_dir = Path(tmp) / "memory"
            memory_dir.mkdir()

            save_pipeline_artifact(str(memory_dir), "api_analysis_feedback.json", {
                "feedback": "test feedback",
                "api_summary": [],
            })
            save_pipeline_state(str(memory_dir), "validate_urls")

            state = {"memory_dir": str(memory_dir)}
            result = _route_resume(state)
            # 应优先路由到 analyze_api 而不是 save_interfaces
            assert result == "analyze_api"

    def should_follow_pipeline_state_when_no_feedback(self):
        """无 feedback 文件时正常按 pipeline_state 路由
        Without feedback files, should follow pipeline_state.json."""
        from graph.workflow import _route_resume

        with tempfile.TemporaryDirectory() as tmp:
            memory_dir = Path(tmp) / "memory"
            memory_dir.mkdir()

            save_pipeline_state(str(memory_dir), "parse_docs")

            state = {"memory_dir": str(memory_dir)}
            result = _route_resume(state)
            assert result == "analyze_api"  # parse_docs → analyze_api

    def should_return_batch_controller_when_no_memory_dir(self):
        """无 memory_dir 时返回 batch_controller
        When no memory_dir, return batch_controller."""
        from graph.workflow import _route_resume

        state = {"memory_dir": ""}
        result = _route_resume(state)
        assert result == "batch_controller"
