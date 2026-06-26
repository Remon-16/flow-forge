"""Tests for executor.biz_flow — BizFlowExecutor."""

import threading
from unittest.mock import MagicMock, Mock, patch

import pytest
import requests

from executor.biz_flow import BizFlowExecutor, InheritResolutionError
from processors.base import ProcessorError


class TestBizFlowExecutorTest:

    @staticmethod
    def _make_step(**overrides):
        step = {
            "step_id": "S001",
            "api_name": "GetUser",
            "app_name": "my_app",
            "method": "GET",
            "url": "/api/user",
            "request_head": {"Content-Type": "application/json"},
            "request_body": {},
            "status_code": 200,
            "assert_dict": {},
            "assert_rules": [],
            "preprocessors": [],
            "postprocessors": [],
        }
        step.update(overrides)
        return step

    @staticmethod
    def _make_biz_flow(**overrides):
        flow = {
            "sheet_name": "TestFlow",
            "steps": [],
            "parse_error": None,
        }
        flow.update(overrides)
        return flow

    @staticmethod
    def _make_mock_response(status=200, json_body=None):
        resp = Mock(spec=requests.Response)
        resp.status_code = status
        resp.headers = {"Content-Type": "application/json"}
        resp.json.return_value = json_body if json_body is not None else {"ok": True}
        resp.text = '{"ok": true}'
        return resp

    @staticmethod
    def _make_passing_assertions():
        return [{"field": "status_code", "expected": 200, "actual": 200, "passed": True}]

    @staticmethod
    def _make_failing_assertions():
        return [{"field": "status_code", "expected": 200, "actual": 500, "passed": False}]

    # ------------------------------------------------------------------
    # Multi-step success
    # ------------------------------------------------------------------

    @patch("executor.biz_flow.get_app")
    def should_execute_multi_step_flow_successfully(self, mock_get_app):
        mock_get_app.return_value = {"baseURL": "https://api.example.com"}

        response = self._make_mock_response(200)
        assertions = self._make_passing_assertions()

        executor = BizFlowExecutor({})
        executor._step_data = threading.local()

        step1 = self._make_step(step_id="S001", url="/api/login")
        step2 = self._make_step(step_id="S002", url="/api/data")
        flow = self._make_biz_flow(steps=[step1, step2])

        with patch.object(executor, "_send_request", return_value=response), \
             patch.object(executor, "_run_assertions", return_value=assertions), \
             patch("executor.biz_flow.LoginManager.resolve_token",
                   return_value=({"Content-Type": "application/json"}, None)), \
             patch.object(executor, "_load_processors", return_value=None):
            result = executor.execute_single(flow)

        assert result["passed"] is True
        assert result["sheet_name"] == "TestFlow"
        assert len(result["steps"]) == 2
        assert result["flow_chain"] == "GetUser → GetUser"
        assert result["failed_step"] is None
        assert all(s["passed"] for s in result["steps"])

    # ------------------------------------------------------------------
    # Break on first failed step
    # ------------------------------------------------------------------

    @patch("executor.biz_flow.get_app")
    def should_break_on_first_failed_step(self, mock_get_app):
        mock_get_app.return_value = {"baseURL": "https://api.example.com"}

        response = self._make_mock_response(200)
        pass_assertions = self._make_passing_assertions()
        fail_assertions = self._make_failing_assertions()

        executor = BizFlowExecutor({})
        executor._step_data = threading.local()

        step1 = self._make_step(step_id="S001", url="/api/login")
        step2 = self._make_step(step_id="S002", url="/api/order")
        step3 = self._make_step(step_id="S003", url="/api/confirm")
        flow = self._make_biz_flow(steps=[step1, step2, step3])

        call_count = [0]

        def side_effect_send(*args, **kwargs):
            call_count[0] += 1
            return response

        def side_effect_assertions(*args, **kwargs):
            call_count[0]  # access for side-effect tracking by call order
            if call_count[0] == 1:
                return pass_assertions  # step 1 passes
            else:
                return fail_assertions  # step 2 fails

        with patch.object(executor, "_send_request", side_effect=side_effect_send) as mock_send, \
             patch.object(executor, "_run_assertions", side_effect=side_effect_assertions), \
             patch("executor.biz_flow.LoginManager.resolve_token",
                   return_value=({"Content-Type": "application/json"}, None)), \
             patch.object(executor, "_load_processors", return_value=None):
            result = executor.execute_single(flow)

        # Step 2 failed, step 3 should not have executed
        assert result["passed"] is False
        assert result["failed_step"] == "S002"
        assert len(result["steps"]) == 2  # only first two steps executed
        assert mock_send.call_count == 2  # only two requests made

    # ------------------------------------------------------------------
    # Parse error
    # ------------------------------------------------------------------

    def should_fail_on_parse_error(self):
        executor = BizFlowExecutor({})
        flow = self._make_biz_flow(parse_error="Invalid inherit format")

        result = executor.execute_single(flow)

        assert result["passed"] is False
        assert result["parse_error"] == "Invalid inherit format"
        assert result["steps"] == []

    # ------------------------------------------------------------------
    # Empty steps
    # ------------------------------------------------------------------

    def should_fail_on_empty_steps(self):
        executor = BizFlowExecutor({})
        flow = self._make_biz_flow(steps=[])

        result = executor.execute_single(flow)

        assert result["passed"] is False
        assert "no steps to execute" in result["error"]

    # ------------------------------------------------------------------
    # Preprocessor error per step
    # ------------------------------------------------------------------

    @patch("executor.biz_flow.get_app")
    def should_fail_on_preprocessor_error_per_step(self, mock_get_app):
        mock_get_app.return_value = {"baseURL": "https://api.example.com"}

        executor = BizFlowExecutor({})
        executor._step_data = threading.local()

        step = self._make_step(step_id="S001", preprocessors=[{"name": "bad_pre"}])
        flow = self._make_biz_flow(steps=[step])

        with patch("executor.biz_flow.LoginManager.resolve_token",
                   return_value=({"Content-Type": "application/json"}, None)), \
             patch.object(executor, "_load_processors", return_value={}), \
             patch.object(executor, "_run_preprocessors") as mock_run_pre:
            mock_run_pre.side_effect = ProcessorError("sign error", processor_name="bad_pre")
            result = executor.execute_single(flow)

        assert result["passed"] is False
        assert result["failed_step"] == "S001"
        step_result = result["steps"][0]
        assert step_result["passed"] is False
        assert "[bad_pre]" in step_result["error"]

    # ------------------------------------------------------------------
    # Postprocessor error per step
    # ------------------------------------------------------------------

    @patch("executor.biz_flow.get_app")
    def should_fail_on_postprocessor_error_per_step(self, mock_get_app):
        mock_get_app.return_value = {"baseURL": "https://api.example.com"}

        response = self._make_mock_response(200)
        assertions = self._make_passing_assertions()

        executor = BizFlowExecutor({})
        executor._step_data = threading.local()

        step = self._make_step(step_id="S001", postprocessors=[{"name": "bad_post"}])
        flow = self._make_biz_flow(steps=[step])

        with patch.object(executor, "_send_request", return_value=response), \
             patch.object(executor, "_run_assertions", return_value=assertions), \
             patch("executor.biz_flow.LoginManager.resolve_token",
                   return_value=({"Content-Type": "application/json"}, None)), \
             patch.object(executor, "_load_processors", return_value={}), \
             patch.object(executor, "_run_postprocessors") as mock_run_post:
            mock_run_post.side_effect = ProcessorError("validation error", processor_name="bad_post")
            result = executor.execute_single(flow)

        assert result["passed"] is False
        assert result["failed_step"] == "S001"
        step_result = result["steps"][0]
        assert step_result["passed"] is False
        assert "[bad_post]" in step_result["error"]

    # ------------------------------------------------------------------
    # URL not exist in step
    # ------------------------------------------------------------------

    def should_handle_url_not_exist_in_step(self):
        executor = BizFlowExecutor({})
        executor._step_data = threading.local()

        step = self._make_step(step_id="S001", url="/api/<URL not exist>")
        flow = self._make_biz_flow(steps=[step])

        result = executor.execute_single(flow)

        assert result["passed"] is False
        assert result["failed_step"] == "S001"
        step_result = result["steps"][0]
        assert "URL not found" in step_result["error"]

    # ------------------------------------------------------------------
    # InheritResolutionError handling
    # ------------------------------------------------------------------

    @patch("executor.biz_flow.get_app")
    def should_handle_inherit_resolution_error(self, mock_get_app):
        mock_get_app.return_value = {"baseURL": "https://api.example.com"}

        executor = BizFlowExecutor({})
        executor._step_data = threading.local()

        step = self._make_step(step_id="S001", inherit="bad_ref")
        flow = self._make_biz_flow(steps=[step])

        with patch.object(executor, "_parse_inherit") as mock_parse:
            mock_parse.side_effect = InheritResolutionError("Invalid inherit reference")

            result = executor.execute_single(flow)

        assert result["passed"] is False
        step_result = result["steps"][0]
        assert "Inherit resolution error" in step_result["error"]

    # ------------------------------------------------------------------
    # _parse_inherit dict format
    # ------------------------------------------------------------------

    def should_parse_inherit_dict_format(self):
        executor = BizFlowExecutor({})
        inherit = {"myVar": "S001.token"}
        result = executor._parse_inherit(inherit)

        assert result == {"myVar": ("S001", "token")}

    def should_parse_inherit_without_dot_path(self):
        executor = BizFlowExecutor({})
        inherit = {"myVar": "S001"}
        result = executor._parse_inherit(inherit)

        assert result == {"myVar": ("S001", "")}

    def should_parse_inherit_old_string_format(self):
        executor = BizFlowExecutor({})
        inherit = "myVar=S001.token, otherVar=S002.id"
        result = executor._parse_inherit(inherit)

        assert result == {"myVar": ("S001", "token"), "otherVar": ("S002", "id")}

    def should_ignore_empty_pairs_in_inherit(self):
        executor = BizFlowExecutor({})
        # Invalid pairs should be skipped
        result = executor._parse_inherit(",,")
        assert result == {}

        result = executor._parse_inherit(" =value")
        assert result == {}

    # ------------------------------------------------------------------
    # Token resolution — conditional (headTokenName + #{} in header)
    # ------------------------------------------------------------------

    @patch("executor.biz_flow.get_app")
    def should_skip_token_resolution_when_no_placeholder(self, mock_get_app):
        """Token resolution should be skipped when headTokenName header has no #{...} placeholder."""
        mock_get_app.return_value = {
            "baseURL": "https://api.example.com",
            "headTokenName": "Authorization",
        }

        response = self._make_mock_response(200)
        assertions = self._make_passing_assertions()

        mock_resolve = MagicMock()

        executor = BizFlowExecutor({})
        executor._step_data = threading.local()

        step = self._make_step(
            step_id="S001",
            request_head={"Authorization": "Bearer static-token"},
        )
        flow = self._make_biz_flow(steps=[step])

        with patch.object(executor, "_send_request", return_value=response), \
             patch.object(executor, "_run_assertions", return_value=assertions), \
             patch("executor.biz_flow.LoginManager.resolve_token", mock_resolve), \
             patch.object(executor, "_load_processors", return_value=None):
            result = executor.execute_single(flow)

        assert result["passed"] is True
        # resolve_token should NOT have been called — no placeholder in header
        mock_resolve.assert_not_called()

    # ------------------------------------------------------------------
    # Thread safety — _step_data isolation
    # ------------------------------------------------------------------

    def should_have_thread_local_step_data(self):
        executor = BizFlowExecutor({})
        assert hasattr(executor, "_step_data")
        assert isinstance(executor._step_data, threading.local)
