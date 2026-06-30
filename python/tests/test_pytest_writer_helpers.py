"""Tests for the standalone helper functions generated in conftest.py.

These tests verify that every helper function produced by the pytest code
generator behaves correctly.  The functions are loaded from a generated
conftest.py in a temporary directory.
"""

import hashlib
import hmac
import json
import logging
import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(scope="module")
def helpers():
    """Write the generated conftest.py to a temp dir and return its module."""
    from converter.pytest_writer import _CONFTEST_TEMPLATE

    d = tempfile.mkdtemp()
    conftest_path = os.path.join(d, "conftest.py")
    with open(conftest_path, "w", encoding="utf-8") as f:
        f.write(_CONFTEST_TEMPLATE)

    # Create _config.py with test app (token helpers import from it)
    config_path = os.path.join(d, "_config.py")
    with open(config_path, "w", encoding="utf-8") as f:
        f.write('''ENV = "test"
APPS = {
    "testApp": {
        "baseURL": "http://localhost:9999",
        "loginPath": "/auth/login",
        "headTokenName": "Authorization",
        "loginBody": "username,password",
        "resTokenPath": "data.token",
        "user1": {"username": "admin", "password": "secret"},
    }
}
''')

    sys.path.insert(0, d)
    import conftest
    return conftest


# ============================================================================
# _resolve_path
# ============================================================================

class TestResolvePath:
    def should_resolve_simple_dict_path(self, helpers):
        data = {"a": {"b": {"c": 42}}}
        assert helpers._resolve_path(data, "a.b.c") == 42

    def should_resolve_bracket_index(self, helpers):
        data = {"items": [10, 20, 30]}
        assert helpers._resolve_path(data, "items[1]") == 20

    def should_resolve_dot_with_index(self, helpers):
        data = {"data": {"records": [{"id": 1}, {"id": 2}]}}
        assert helpers._resolve_path(data, "data.records.1.id") == 2

    def should_strip_dollar_prefix(self, helpers):
        data = {"data": {"token": "abc123"}}
        assert helpers._resolve_path(data, "$.data.token") == "abc123"

    def should_return_missing_for_bad_index(self, helpers):
        data = [1, 2]
        result = helpers._resolve_path(data, "5")
        assert isinstance(result, helpers._Missing)

    def should_return_missing_for_missing_key(self, helpers):
        data = {"a": 1}
        result = helpers._resolve_path(data, "b")
        assert isinstance(result, helpers._Missing)

    def should_handle_none_intermediate(self, helpers):
        data = {"a": None}
        result = helpers._resolve_path(data, "a.b.c")
        assert isinstance(result, helpers._Missing)

    def should_handle_empty_path(self, helpers):
        result = helpers._resolve_path({"a": 1}, "")
        assert isinstance(result, helpers._Missing)


# ============================================================================
# _resolve_url
# ============================================================================

class TestResolveUrl:
    def should_resolve_hash_placeholder(self, helpers):
        url = helpers._resolve_url("/api/users/#{id}", {"id": "42"})
        assert url == "/api/users/42"

    def should_resolve_curly_placeholder(self, helpers):
        url = helpers._resolve_url("/api/stores/{id}", {"id": "88"})
        assert url == "/api/stores/88"

    def should_resolve_mixed_placeholders(self, helpers):
        url = helpers._resolve_url("/api/#{a}/{b}", {"a": "1", "b": "2"})
        assert url == "/api/1/2"

    def should_leave_unresolved_when_key_missing(self, helpers):
        url = helpers._resolve_url("/api/{missing}", {"other": "x"})
        assert url == "/api/{missing}"

    def should_handle_url_without_placeholders(self, helpers):
        url = helpers._resolve_url("/api/static", {"a": "1"})
        assert url == "/api/static"


# ============================================================================
# _assert_field
# ============================================================================

class TestAssertField:
    def should_pass_when_values_match(self, helpers):
        assert helpers._assert_field({"status": "ok"}, "status", "ok") is True

    def should_fail_when_values_differ(self, helpers):
        assert helpers._assert_field({"status": "ok"}, "status", "error") is False

    def should_fail_when_path_missing(self, helpers):
        assert helpers._assert_field({}, "missing.path", "x") is False

    def should_fail_when_data_is_none(self, helpers):
        assert helpers._assert_field(None, "path", "x") is False

    def should_use_string_comparison(self, helpers):
        assert helpers._assert_field({"count": 5}, "count", "5") is True


# ============================================================================
# _assert_rules — operators
# ============================================================================

class TestAssertRules:
    def should_pass_all_rules(self, helpers):
        data = {"items": [{"price": 10}, {"price": 20}], "total": 30, "name": "test"}
        rules = [
            "items.length() >= 2",
            "total == 30",
            "name contains test",
        ]
        results = helpers._assert_rules(data, rules)
        assert all(r["passed"] for r in results)

    def should_detect_failing_rule(self, helpers):
        data = {"total": 5}
        results = helpers._assert_rules(data, ["total > 10"])
        assert results[0]["passed"] is False

    def should_handle_parse_error_gracefully(self, helpers):
        results = helpers._assert_rules({}, ["garbage!!! without operator"])
        assert results[0]["passed"] is False
        assert "error" in str(results[0]["actual"])


class TestExecuteOp:
    def eq_should_pass(self, helpers):
        assert helpers._execute_op(42, "==", 42) is True

    def eq_should_fail(self, helpers):
        assert helpers._execute_op(42, "==", 0) is False

    def ne_should_pass(self, helpers):
        assert helpers._execute_op(1, "!=", 2) is True

    def gt_should_pass(self, helpers):
        assert helpers._execute_op(10, ">", 5) is True

    def ge_should_pass(self, helpers):
        assert helpers._execute_op(5, ">=", 5) is True

    def lt_should_pass(self, helpers):
        assert helpers._execute_op(3, "<", 5) is True

    def le_should_pass(self, helpers):
        assert helpers._execute_op(3, "<=", 3) is True

    def regex_should_pass(self, helpers):
        assert helpers._execute_op("hello123", "=~", r"hello\d+") is True

    def in_should_pass(self, helpers):
        assert helpers._execute_op("a", "in", ["a", "b"]) is True

    def contains_should_pass(self, helpers):
        assert helpers._execute_op("hello world", "contains", "world") is True

    def not_contains_should_pass(self, helpers):
        assert helpers._execute_op("hello", "not_contains", "x") is True

    def is_null_should_pass(self, helpers):
        assert helpers._execute_op(None, "is_null", None) is True

    def is_not_null_should_pass(self, helpers):
        assert helpers._execute_op("value", "is_not_null", None) is True

    def typeof_should_pass(self, helpers):
        assert helpers._execute_op(42, "typeof", "int") is True

    def typeof_should_fail(self, helpers):
        assert helpers._execute_op(42, "typeof", "str") is False


class TestEvalExpression:
    def should_resolve_simple_path(self, helpers):
        assert helpers._eval_expression("data.x", {"data": {"x": 5}}) == 5

    def should_resolve_length(self, helpers):
        assert helpers._eval_expression("data.list.length()", {"data": {"list": [1, 2, 3]}}) == 3

    def should_resolve_sum(self, helpers):
        data = {"items": [{"price": 10}, {"price": 20}]}
        assert helpers._eval_expression("SUM(items[*].price)", data) == 30.0

    def should_resolve_sum_product(self, helpers):
        data = {"items": [{"a": 2, "b": 3}, {"a": 4, "b": 5}]}
        result = helpers._eval_expression("SUM_PRODUCT(items[*].a, items[*].b)", data)
        assert result == 2 * 3 + 4 * 5  # 26.0

    def should_handle_missing_path(self, helpers):
        with pytest.raises(ValueError, match="Path not found"):
            helpers._eval_expression("missing", {})


# ============================================================================
# _resolve_token / _do_login
# ============================================================================

class TestResolveToken:
    @pytest.fixture(autouse=True)
    def clear_token_cache(self, helpers):
        helpers._token_cache.clear()
        yield
        helpers._token_cache.clear()

    def should_return_headers_unchanged_when_no_placeholder(self, helpers):
        headers = {"Authorization": "Bearer fixed-token"}
        result = helpers._resolve_token(headers, "testApp")
        assert result == headers

    def should_return_headers_unchanged_when_app_unknown(self, helpers):
        headers = {"Authorization": "#{user1}"}
        result = helpers._resolve_token(headers, "unknownApp")
        assert result == headers

    @patch("requests.post")
    def should_resolve_token_placeholder(self, mock_post, helpers):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": {"token": "jwt-token-123"}}
        mock_post.return_value = mock_resp

        headers = {"Authorization": "Bearer #{user1}"}
        result = helpers._resolve_token(headers, "testApp")
        assert result["Authorization"] == "Bearer jwt-token-123"

    @patch("requests.post")
    def should_cache_token(self, mock_post, helpers):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": {"token": "cached-token"}}
        mock_post.return_value = mock_resp

        helpers._resolve_token({"Authorization": "#{user1}"}, "testApp")
        helpers._resolve_token({"Authorization": "#{user1}"}, "testApp")
        assert mock_post.call_count == 1  # second call uses cache


# ============================================================================
# Built-in processor helpers
# ============================================================================

class TestApplyTimestamp:
    def should_add_timestamp_and_request_id(self, helpers):
        headers = {}
        helpers._apply_timestamp(headers)
        assert "X-Timestamp" in headers
        assert "X-Request-Id" in headers

    def should_use_custom_header_names(self, helpers):
        headers = {}
        helpers._apply_timestamp(headers, {
            "header_timestamp": "X-Custom-TS",
            "header_request_id": "X-Custom-RID",
        })
        assert "X-Custom-TS" in headers
        assert "X-Custom-RID" in headers

    def should_produce_iso8601_timestamp(self, helpers):
        import re
        headers = {}
        helpers._apply_timestamp(headers)
        # ISO 8601: 2024-01-15T10:30:00.123456+00:00 or similar
        iso_re = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
        assert iso_re.search(headers["X-Timestamp"])


class TestApplyHmacSign:
    @patch.dict(os.environ, {"SIGN_SECRET": "my-secret"})
    def should_add_signature_header(self, helpers):
        headers = {}
        body = {"key": "value"}
        helpers._apply_hmac_sign(headers, body)
        assert "X-Signature" in headers

    @patch.dict(os.environ, {"SIGN_SECRET": "my-secret"})
    def should_produce_deterministic_signature(self, helpers):
        headers1 = {}
        headers2 = {}
        body = {"key": "value"}
        helpers._apply_hmac_sign(headers1, body)
        helpers._apply_hmac_sign(headers2, body)
        assert headers1["X-Signature"] == headers2["X-Signature"]

    def should_skip_when_secret_empty(self, helpers, caplog):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("SIGN_SECRET", None)
            headers = {}
            helpers._apply_hmac_sign(headers, {})
            assert "X-Signature" not in headers


class TestVerifyHmac:
    def should_not_raise_on_match(self, helpers):
        secret = "test-secret"
        body = {"result": "ok"}
        body_str = json.dumps(body, ensure_ascii=False, sort_keys=True)

        with patch.dict(os.environ, {"SIGN_SECRET": secret}):
            headers = {
                "X-Signature": hmac.new(
                    secret.encode(), body_str.encode(), hashlib.sha256,
                ).hexdigest(),
            }
            helpers._verify_hmac(headers, body)  # should not raise

    def should_raise_on_mismatch(self, helpers):
        with patch.dict(os.environ, {"SIGN_SECRET": "secret"}):
            with pytest.raises(AssertionError, match="HMAC signature mismatch"):
                helpers._verify_hmac({"X-Signature": "bad"}, {"result": "ok"})

    def should_raise_on_missing_header(self, helpers):
        with patch.dict(os.environ, {"SIGN_SECRET": "secret"}):
            with pytest.raises(AssertionError, match="not found"):
                helpers._verify_hmac({}, {"result": "ok"})


class TestPrintRequest:
    def should_log_request_summary(self, helpers, caplog):
        with caplog.at_level(logging.INFO):
            helpers._print_request({"Content-Type": "json"}, {"a": 1})
        assert "Content-Type" in caplog.text


class TestPrintResponse:
    def should_log_response_summary(self, helpers, caplog):
        with caplog.at_level(logging.INFO):
            helpers._print_response({"Content-Type": "json"}, {"status": "ok"})
        assert "Content-Type" in caplog.text


class TestLogResponseMetrics:
    def should_log_content_length(self, helpers, caplog):
        with caplog.at_level(logging.INFO):
            helpers._log_response_metrics({"Content-Length": "500"}, None)
        assert "500" in caplog.text

    def should_warn_when_exceeds_threshold(self, helpers, caplog):
        with caplog.at_level(logging.WARNING):
            helpers._log_response_metrics(
                {"Content-Length": "2000000"}, None, threshold=100
            )
        assert "exceeds threshold" in caplog.text

    def should_compute_from_body_when_no_header(self, helpers, caplog):
        with caplog.at_level(logging.INFO):
            helpers._log_response_metrics({}, "hello")
        # len("hello".encode("utf-8")) == 5
        assert "5 bytes" in caplog.text

    def should_handle_missing_content_length(self, helpers, caplog):
        with caplog.at_level(logging.INFO):
            helpers._log_response_metrics({}, None)
        assert "unknown" in caplog.text.lower()
