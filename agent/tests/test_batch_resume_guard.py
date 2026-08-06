"""Tests for batch_controller resume guard — plan_parsed 缺失时应当报错。

batch_controller resume 防护测试 — 当 plan_parsed 为 None 时，不再构造虚假 TestPlan。
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from config.settings import Settings
from graph.nodes.batch import batch_controller_node
from graph.nodes.helpers import configure


# ---------------------------------------------------------------------------
# 共享 fixtures / Shared fixtures
# ---------------------------------------------------------------------------


def _make_state(**overrides):
    """构造测试用 GraphState / Build minimal GraphState dict for testing."""
    state = {
        "plan_parsed": None,
        "interfaces": [],
        "output_dir": "/tmp/output",
        "cases_dir": "/tmp/output/cases",
        "user_guidance": "",
        "batch_size": 10,
        "reference_dir": "",
        "api_summary": [],
        "case_type": "both",
        "resume": True,
        "api_paths": [],
        "api_raw_text": "",
        "memory_dir": "",
        "errors": [],
        "debug_snapshots": False,
        "output_format": "yaml",
        "resume_overwrite": False,
        "auto_mode": True,
        "plan_confirmed": True,
        "plan_feedback": "",
        "plan_feedback_type": "text",
        "plan_annotations": [],
        "requirement_texts": [],
        "requirement_analysis": {},
        "requirement_paths": [],
        "parse_mode": "llm",
        "parser_path": "",
        "api_summary_feedback": "",
        "api_summary_confirmed": True,
    }
    state.update(overrides)
    return state


def _setup_settings():
    """确保模块级 _settings 已注入 / Ensure module-level _settings is injected."""
    s = Settings(llm_api_key="test")
    s.auto_mode = True
    s.plugin_batch_size = 10
    configure(s, None)
    return s


# ---------------------------------------------------------------------------
# TestBatchResumeGuard / batch_controller resume 防护
# ---------------------------------------------------------------------------


class TestBatchResumeGuard:
    """batch_controller resume 时 plan_parsed 缺失测试。"""

    def should_error_when_plan_is_none_in_resume(self):
        """plan_parsed=None 且 resume=True 时 errors 列表应非空
        When plan_parsed is None and resume=True, errors should be non-empty."""
        _setup_settings()
        state = _make_state(plan_parsed=None, resume=True, interfaces=[{"test_id": "api_1"}])

        result = batch_controller_node(state)
        assert len(result["errors"]) > 0
        assert "plan" in result["errors"][0].lower() or "plan_parsed" in result["errors"][0]

    def should_error_when_plan_is_none_and_no_interfaces(self):
        """plan_parsed=None 且 interfaces 为空时也应报错
        Should also error when both plan and interfaces are empty."""
        _setup_settings()
        state = _make_state(plan_parsed=None, resume=True, interfaces=[])

        result = batch_controller_node(state)
        assert len(result["errors"]) > 0

    def should_proceed_normally_when_plan_exists(self):
        """plan_parsed 存在时应正常进入 BatchController
        When plan_parsed exists, should proceed to BatchController normally."""
        _setup_settings()
        from models.schema import PlanStep, TestPlan

        plan = TestPlan(
            business_summary="Test plan",
            single_test_points={"api_1": [
                PlanStep(test_id="TP_001", description="Positive test", tag="P0", scenario_type="positive"),
            ]},
        )
        state = _make_state(plan_parsed=plan, resume=True, interfaces=[{"test_id": "api_1"}])

        # BatchController.run 会调用 LLM, 需要 mock
        with patch("agents.batch_controller.BatchController.run",
                   return_value={"single_cases": [], "biz_flows": [], "failures": []}):
            result = batch_controller_node(state)

        # 应该没有 plan_missing 错误 / Should NOT have plan_missing error
        plan_errors = [e for e in result["errors"] if "plan_parsed" in e]
        assert len(plan_errors) == 0

    def should_not_error_when_not_in_resume_mode(self):
        """非 resume 模式下 plan_parsed 为 None 也会报错（计划未生成）
        Even in non-resume mode, missing plan is an error (plan not yet generated)."""
        _setup_settings()
        state = _make_state(plan_parsed=None, resume=False, interfaces=[{"test_id": "api_1"}])

        result = batch_controller_node(state)
        assert len(result["errors"]) > 0


# ---------------------------------------------------------------------------
# TestBatchResumeInterfaceRecovery / resume 时 interfaces 恢复
# ---------------------------------------------------------------------------


class TestBatchResumeInterfaceRecovery:
    """resume 时从 YAML 恢复 interfaces 的测试。"""

    def should_restore_interfaces_from_yaml_in_resume(self):
        """resume 时 interfaces 为空应从 YAML 恢复 / Restore interfaces from YAML on resume."""
        _setup_settings()

        with tempfile.TemporaryDirectory() as tmp:
            cases_dir = Path(tmp) / "cases"
            ifaces_dir = cases_dir / "interfaces"
            ifaces_dir.mkdir(parents=True)

            # 创建一个 YAML 接口文件 / Create a YAML interface file
            yaml_content = (
                "test_id: api_login\n"
                "api_name: User Login\n"
                "method: POST\n"
                "url: /api/login\n"
            )
            (ifaces_dir / "api_login.yaml").write_text(yaml_content, encoding="utf-8")

            from models.schema import PlanStep, TestPlan

            plan = TestPlan(
                business_summary="Test",
                single_test_points={"api_login": [
                    PlanStep(test_id="TP_001", description="Test", tag="P0", scenario_type="positive"),
                ]},
            )

            state = _make_state(
                plan_parsed=plan,
                interfaces=[],
                cases_dir=str(cases_dir),
                output_dir=str(tmp),
                resume=True,
            )

            with patch("agents.batch_controller.BatchController.run",
                       return_value={"single_cases": [], "biz_flows": [], "failures": []}):
                result = batch_controller_node(state)

            # interfaces 应从 YAML 恢复 / interfaces should be restored from YAML
            assert len(result["interfaces"]) >= 1
