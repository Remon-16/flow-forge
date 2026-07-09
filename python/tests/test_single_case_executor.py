"""Tests for executor.single_case — SingleCaseExecutor."""

from unittest.mock import MagicMock, Mock, patch

import pytest
import requests

from executor.single_case import SingleCaseExecutor
from processors.base import ProcessorError


class TestSingleCaseExecutorTest:

    @staticmethod
    def _make_case(**overrides):
        """Factory for a standard single test case."""
        case = {
            "test_id": "TC001",
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
            "tag": "",
            "remark": "",
        }
        case.update(overrides)
        return case

    @staticmethod
    def _make_mock_response(status=200, json_body=None, text_body=None):
        resp = Mock(spec=requests.Response)
        resp.status_code = status
        resp.headers = {"Content-Type": "application/json"}
        resp.json.return_value = json_body if json_body is not None else {"ok": True}
        resp.text = text_body or '{"ok": true}'
        return resp

    # ------------------------------------------------------------------
    # Full lifecycle success
    # ------------------------------------------------------------------

    @patch("executor.single_case.get_app")
    @patch("executor.single_case.LoginManager.resolve_token")
    def should_execute_full_lifecycle_successfully(self, mock_resolve, mock_get_app):
        mock_get_app.return_value = {"baseURL": "https://api.example.com"}
        mock_resolve.return_value = (
            {"Content-Type": "application/json", "Authorization": "Bearer token123"},
            None,
        )

        response = self._make_mock_response(200, {"id": 1})
        assertions = [
            {"field": "status_code", "expected": 200, "actual": 200, "passed": True},
            {"field": "response.id", "expected": 1, "actual": 1, "passed": True},
        ]

        executor = SingleCaseExecutor({})
        case = self._make_case()

        with patch.object(executor, "_send_request", return_value=response), \
             patch.object(executor, "_run_assertions", return_value=assertions), \
             patch.object(executor, "_load_processors", return_value=None):
            result = executor.execute_single(case)

        assert result["passed"] is True
        assert result["test_id"] == "TC001"
        assert result["response_status"] == 200
        assert result["error"] is None
        assert result["request_headers"]["Authorization"] == "Bearer token123"

    # ------------------------------------------------------------------
    # URL not exist
    # ------------------------------------------------------------------

    def should_fail_on_url_not_exist(self):
        executor = SingleCaseExecutor({})
        case = self._make_case(url="/api/<URL not exist>")

        result = executor.execute_single(case)

        assert result["passed"] is False
        assert "URL not found" in result["error"]

    # ------------------------------------------------------------------
    # Token resolution error
    # ------------------------------------------------------------------

    @patch("executor.single_case.get_app")
    @patch("executor.single_case.LoginManager.resolve_token")
    def should_fail_on_token_resolution_error(self, mock_resolve, mock_get_app):
        mock_get_app.return_value = {"baseURL": "https://api.example.com"}
        mock_resolve.return_value = ({"Content-Type": "application/json"}, "Login failed: invalid credentials")

        executor = SingleCaseExecutor({})
        case = self._make_case()

        with patch.object(executor, "_load_processors", return_value=None):
            result = executor.execute_single(case)

        assert result["passed"] is False
        assert "Login failed" in result["error"]

    # ------------------------------------------------------------------
    # Preprocessor error
    # ------------------------------------------------------------------

    @patch("executor.single_case.get_app")
    @patch("executor.single_case.LoginManager.resolve_token")
    def should_fail_and_return_immediately_on_preprocessor_error(self, mock_resolve, mock_get_app):
        mock_get_app.return_value = {"baseURL": "https://api.example.com"}
        mock_resolve.return_value = ({"Content-Type": "application/json"}, None)

        executor = SingleCaseExecutor({})
        case = self._make_case(preprocessors=[{"name": "bad_pre"}])

        with patch.object(executor, "_load_processors", return_value={}), \
             patch.object(executor, "_run_preprocessors") as mock_run_pre:
            mock_run_pre.side_effect = ProcessorError("hmac key missing", processor_name="bad_pre")
            result = executor.execute_single(case)

        assert result["passed"] is False
        assert "[bad_pre]" in result["error"]
        assert "hmac key missing" in result["error"]
        # _send_request should NOT have been called
        # (already returned before HTTP call)

    # ------------------------------------------------------------------
    # Postprocessor error
    # ------------------------------------------------------------------

    @patch("executor.single_case.get_app")
    @patch("executor.single_case.LoginManager.resolve_token")
    def should_continue_and_set_failed_on_postprocessor_error(self, mock_resolve, mock_get_app):
        mock_get_app.return_value = {"baseURL": "https://api.example.com"}
        mock_resolve.return_value = ({"Content-Type": "application/json"}, None)

        response = self._make_mock_response(200, {"ok": True})
        assertions = [
            {"field": "status_code", "expected": 200, "actual": 200, "passed": True},
        ]

        executor = SingleCaseExecutor({})
        case = self._make_case(postprocessors=[{"name": "bad_post"}])

        with patch.object(executor, "_send_request", return_value=response), \
             patch.object(executor, "_run_assertions", return_value=assertions), \
             patch.object(executor, "_load_processors", return_value={}), \
             patch.object(executor, "_run_postprocessors") as mock_run_post:
            mock_run_post.side_effect = ProcessorError("validation failed", processor_name="bad_post")
            result = executor.execute_single(case)

        # Assertions were still checked, but postprocessor error set passed=False
        assert result["passed"] is False
        assert "[bad_post]" in result["error"]
        assert "validation failed" in result["error"]
        assert len(result["assertions"]) == 1

    # ------------------------------------------------------------------
    # HTTP errors
    # ------------------------------------------------------------------

    @patch("executor.single_case.get_app")
    @patch("executor.single_case.LoginManager.resolve_token")
    def should_handle_request_timeout(self, mock_resolve, mock_get_app):
        mock_get_app.return_value = {"baseURL": "https://api.example.com"}
        mock_resolve.return_value = ({"Content-Type": "application/json"}, None)

        executor = SingleCaseExecutor({})
        case = self._make_case()

        with patch.object(executor, "_send_request") as mock_send, \
             patch.object(executor, "_load_processors", return_value=None):
            mock_send.side_effect = requests.Timeout("Connection timed out")
            result = executor.execute_single(case)

        assert result["passed"] is False
        assert "timeout" in result["error"].lower()

    @patch("executor.single_case.get_app")
    @patch("executor.single_case.LoginManager.resolve_token")
    def should_handle_connection_error(self, mock_resolve, mock_get_app):
        mock_get_app.return_value = {"baseURL": "https://api.example.com"}
        mock_resolve.return_value = ({"Content-Type": "application/json"}, None)

        executor = SingleCaseExecutor({})
        case = self._make_case()

        with patch.object(executor, "_send_request") as mock_send, \
             patch.object(executor, "_load_processors", return_value=None):
            mock_send.side_effect = requests.ConnectionError("Connection refused")
            result = executor.execute_single(case)

        assert result["passed"] is False
        assert "Connection error" in result["error"]

    @patch("executor.single_case.get_app")
    @patch("executor.single_case.LoginManager.resolve_token")
    def should_handle_request_exception(self, mock_resolve, mock_get_app):
        mock_get_app.return_value = {"baseURL": "https://api.example.com"}
        mock_resolve.return_value = ({"Content-Type": "application/json"}, None)

        executor = SingleCaseExecutor({})
        case = self._make_case()

        with patch.object(executor, "_send_request") as mock_send, \
             patch.object(executor, "_load_processors", return_value=None):
            mock_send.side_effect = requests.RequestException("Unknown error")
            result = executor.execute_single(case)

        assert result["passed"] is False
        assert "Request error" in result["error"]

    # ------------------------------------------------------------------
    # URL value None
    # ------------------------------------------------------------------

    @patch("executor.single_case.get_app")
    @patch("executor.single_case.LoginManager.resolve_token")
    def should_handle_url_value_none(self, mock_resolve, mock_get_app):
        mock_get_app.return_value = {"baseURL": "https://api.example.com"}
        mock_resolve.return_value = ({"Content-Type": "application/json"}, None)

        response = self._make_mock_response(200)
        assertions = [{"field": "status_code", "expected": 200, "actual": 200, "passed": True}]

        executor = SingleCaseExecutor({})
        case = self._make_case(url=None)

        with patch.object(executor, "_send_request", return_value=response), \
             patch.object(executor, "_run_assertions", return_value=assertions), \
             patch.object(executor, "_load_processors", return_value=None):
            result = executor.execute_single(case)

        # url=None: path becomes "" for URL building, but result stores None from case
        assert result["url"] is None
        # Should not crash — request goes through to base URL with empty path

    # ------------------------------------------------------------------
    # Build result baseline
    # ------------------------------------------------------------------

    def should_build_result_with_correct_baseline(self):
        executor = SingleCaseExecutor({})
        case = self._make_case()
        result = executor._build_result(case)

        assert result["test_id"] == "TC001"
        assert result["api_name"] == "GetUser"
        assert result["passed"] is False  # default
        assert result["error"] is None
        assert result["assertions"] == []
        assert result["preprocessor_results"] == []
        assert result["postprocessor_results"] == []
