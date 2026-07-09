"""Tests for processors.runner — run_preprocessors / run_postprocessors."""

from unittest.mock import Mock, patch

import pytest

from processors.base import ProcessorError


# ============================================================================
# Mock processor classes used across tests
# ============================================================================

class _MockPreOk:
    """PreProcessor that modifies headers and body."""
    name = "pre_ok"

    def __init__(self):
        pass

    def can_process(self, case):
        return True

    def process(self, headers, body, case_config, global_config):
        headers["X-Processed"] = "true"
        body["processed"] = True
        return headers, body


class _MockPreSkip:
    """PreProcessor whose can_process returns False."""
    name = "pre_skip"

    def can_process(self, case):
        return False

    def process(self, headers, body, case_config, global_config):
        return headers, body


class _MockPreError:
    """PreProcessor that raises ProcessorError."""
    name = "pre_error"

    def can_process(self, case):
        return True

    def process(self, headers, body, case_config, global_config):
        raise ProcessorError("pre failure", processor_name="pre_error")


class _MockPreGeneric:
    """PreProcessor that raises a generic Exception."""
    name = "pre_generic"

    def can_process(self, case):
        return True

    def process(self, headers, body, case_config, global_config):
        raise RuntimeError("unexpected runtime error")


class _MockPostOk:
    """PostProcessor that succeeds."""
    name = "post_ok"

    def can_process(self, case):
        return True

    def process(self, request_headers, request_body, response_headers,
                response_body, case_config, global_config):
        pass


class _MockPostError:
    """PostProcessor that raises ProcessorError."""
    name = "post_error"

    def can_process(self, case):
        return True

    def process(self, request_headers, request_body, response_headers,
                response_body, case_config, global_config):
        raise ProcessorError("post failure", processor_name="post_error")


class _MockPostGeneric:
    """PostProcessor that raises a generic Exception."""
    name = "post_generic"

    def can_process(self, case):
        return True

    def process(self, request_headers, request_body, response_headers,
                response_body, case_config, global_config):
        raise ValueError("unexpected value error")


# ============================================================================
# RunPreprocessorsTest
# ============================================================================

class TestRunPreprocessorsTest:

    def should_run_single_preprocessor_successfully(self):
        registry = {"pre_ok": _MockPreOk}
        with patch("processors.base._PRE_PROCESSOR_REGISTRY", registry):
            from processors.runner import run_preprocessors

            case = {
                "request_head": {"Content-Type": "application/json"},
                "request_body": {"name": "test"},
                "preprocessors": [{"name": "pre_ok", "config": {}}],
            }
            headers, body, results = run_preprocessors(case, {})

        assert headers["X-Processed"] == "true"
        assert body["processed"] is True
        assert results == [{"name": "pre_ok", "status": "ok"}]

    def should_run_multiple_preprocessors_in_order(self):
        class PreOne:
            name = "pre_one"

            def can_process(self, case):
                return True

            def process(self, headers, body, case_config, global_config):
                headers["order"] = headers.get("order", "") + "1"
                return headers, body

        class PreTwo:
            name = "pre_two"

            def can_process(self, case):
                return True

            def process(self, headers, body, case_config, global_config):
                headers["order"] = headers.get("order", "") + "2"
                return headers, body

        registry = {"pre_one": PreOne, "pre_two": PreTwo}
        with patch("processors.base._PRE_PROCESSOR_REGISTRY", registry):
            from processors.runner import run_preprocessors

            case = {
                "request_head": {},
                "request_body": {},
                "preprocessors": [
                    {"name": "pre_one"},
                    {"name": "pre_two"},
                ],
            }
            headers, body, results = run_preprocessors(case, {})

        assert headers["order"] == "12"
        assert len(results) == 2
        assert results[0]["status"] == "ok"
        assert results[1]["status"] == "ok"

    def should_raise_when_processor_not_in_registry(self):
        registry = {}
        with patch("processors.base._PRE_PROCESSOR_REGISTRY", registry):
            from processors.runner import run_preprocessors

            case = {
                "request_head": {},
                "request_body": {},
                "preprocessors": [{"name": "nonexistent"}],
            }
            with pytest.raises(ProcessorError, match="not found in registry"):
                run_preprocessors(case, {})

    def should_skip_when_can_process_returns_false(self):
        registry = {"pre_skip": _MockPreSkip}
        with patch("processors.base._PRE_PROCESSOR_REGISTRY", registry):
            from processors.runner import run_preprocessors

            case = {
                "request_head": {},
                "request_body": {},
                "preprocessors": [{"name": "pre_skip", "config": {}}],
            }
            headers, body, results = run_preprocessors(case, {})

        assert results == [{"name": "pre_skip", "status": "skipped"}]
        # headers/body unchanged
        assert headers == {}
        assert body == {}

    def should_raise_on_processor_error(self):
        registry = {"pre_error": _MockPreError}
        with patch("processors.base._PRE_PROCESSOR_REGISTRY", registry):
            from processors.runner import run_preprocessors

            case = {
                "request_head": {},
                "request_body": {},
                "preprocessors": [{"name": "pre_error", "config": {}}],
            }
            with pytest.raises(ProcessorError, match="pre failure"):
                run_preprocessors(case, {})

    def should_wrap_generic_exception_in_processor_error(self):
        registry = {"pre_generic": _MockPreGeneric}
        with patch("processors.base._PRE_PROCESSOR_REGISTRY", registry):
            from processors.runner import run_preprocessors

            case = {
                "request_head": {},
                "request_body": {},
                "preprocessors": [{"name": "pre_generic", "config": {}}],
            }
            with pytest.raises(ProcessorError) as exc_info:
                run_preprocessors(case, {})

        assert exc_info.value.processor_name == "pre_generic"
        assert "unexpected runtime error" in str(exc_info.value)

    def should_handle_empty_preprocessors_list(self):
        """When preprocessors is an empty list, nothing changes."""
        registry = {}
        with patch("processors.base._PRE_PROCESSOR_REGISTRY", registry):
            from processors.runner import run_preprocessors

            case = {
                "request_head": {"A": "1"},
                "request_body": {"B": "2"},
                "preprocessors": [],
            }
            headers, body, results = run_preprocessors(case, {})

        assert headers == {"A": "1"}
        assert body == {"B": "2"}
        assert results == []

    def should_handle_missing_request_head_and_body(self):
        """Case has no request_head/body keys."""
        registry = {}
        with patch("processors.base._PRE_PROCESSOR_REGISTRY", registry):
            from processors.runner import run_preprocessors

            case = {
                "preprocessors": [],
            }
            headers, body, results = run_preprocessors(case, {})

        assert headers == {}
        assert body == {}
        assert results == []

    def should_handle_preprocessors_key_none(self):
        """preprocessors key is None instead of list."""
        registry = {}
        with patch("processors.base._PRE_PROCESSOR_REGISTRY", registry):
            from processors.runner import run_preprocessors

            case = {
                "request_head": {"A": "1"},
                "request_body": {"B": "2"},
                "preprocessors": None,
            }
            headers, body, results = run_preprocessors(case, {})

        assert headers == {"A": "1"}
        assert body == {"B": "2"}
        assert results == []


# ============================================================================
# RunPostprocessorsTest
# ============================================================================

class TestRunPostprocessorsTest:

    @staticmethod
    def _make_mock_response(status=200, json_body=None, headers_dict=None):
        resp = Mock()
        resp.status_code = status
        resp.headers = headers_dict or {"Content-Type": "application/json"}
        resp.json.return_value = json_body or {"success": True}
        return resp

    def should_run_single_postprocessor_successfully(self):
        registry = {"post_ok": _MockPostOk}
        with patch("processors.base._POST_PROCESSOR_REGISTRY", registry):
            from processors.runner import run_postprocessors

            case = {
                "request_head": {"Auth": "Bearer x"},
                "request_body": {"q": "test"},
                "postprocessors": [{"name": "post_ok", "config": {}}],
            }
            response = self._make_mock_response()
            results = run_postprocessors(case, response, {})

        assert results == [{"name": "post_ok", "status": "ok"}]

    def should_run_multiple_postprocessors_in_order(self):
        call_order = []

        class PostSeq1:
            name = "post_seq1"

            def can_process(self, case):
                return True

            def process(self, request_headers, request_body, response_headers,
                        response_body, case_config, global_config):
                call_order.append("post_seq1")

        class PostSeq2:
            name = "post_seq2"

            def can_process(self, case):
                return True

            def process(self, request_headers, request_body, response_headers,
                        response_body, case_config, global_config):
                call_order.append("post_seq2")

        registry = {"post_seq1": PostSeq1, "post_seq2": PostSeq2}
        with patch("processors.base._POST_PROCESSOR_REGISTRY", registry):
            from processors.runner import run_postprocessors

            case = {
                "request_head": {},
                "request_body": {},
                "postprocessors": [
                    {"name": "post_seq1"},
                    {"name": "post_seq2"},
                ],
            }
            response = self._make_mock_response()
            results = run_postprocessors(case, response, {})

        assert call_order == ["post_seq1", "post_seq2"]
        assert len(results) == 2

    def should_raise_when_processor_not_in_registry(self):
        registry = {}
        with patch("processors.base._POST_PROCESSOR_REGISTRY", registry):
            from processors.runner import run_postprocessors

            case = {
                "request_head": {},
                "request_body": {},
                "postprocessors": [{"name": "not_found"}],
            }
            response = self._make_mock_response()
            with pytest.raises(ProcessorError, match="not found in registry"):
                run_postprocessors(case, response, {})

    def should_verify_postprocessor_receives_correct_data(self):
        """Postprocessor should receive the correct request and response data."""
        captured = {}

        class InspectPost:
            name = "inspect_post"

            def process(self, request_headers, request_body, response_headers,
                        response_body, case_config, global_config):
                captured["request_headers"] = dict(request_headers)
                captured["request_body"] = dict(request_body)
                captured["response_headers"] = dict(response_headers)
                captured["response_body"] = response_body
                captured["case_config"] = case_config
                captured["global_config"] = global_config

        registry = {"inspect_post": InspectPost}
        with patch("processors.base._POST_PROCESSOR_REGISTRY", registry):
            from processors.runner import run_postprocessors

            case = {
                "request_head": {"Content-Type": "application/json"},
                "request_body": {"id": 123},
                "postprocessors": [{"name": "inspect_post", "config": {"key": "val"}}],
            }
            response = self._make_mock_response(201, json_body={"created": True})
            run_postprocessors(case, response, {"global": "cfg"})

        assert captured["request_headers"]["Content-Type"] == "application/json"
        assert captured["request_body"]["id"] == 123
        assert captured["response_body"] == {"created": True}
        assert captured["response_headers"]["Content-Type"] == "application/json"
        assert captured["case_config"] == {"key": "val"}
        assert captured["global_config"] == {"global": "cfg"}

    def should_raise_on_processor_error(self):
        registry = {"post_error": _MockPostError}
        with patch("processors.base._POST_PROCESSOR_REGISTRY", registry):
            from processors.runner import run_postprocessors

            case = {
                "request_head": {},
                "request_body": {},
                "postprocessors": [{"name": "post_error", "config": {}}],
            }
            response = self._make_mock_response()
            with pytest.raises(ProcessorError, match="post failure"):
                run_postprocessors(case, response, {})

    def should_wrap_generic_exception_in_processor_error(self):
        registry = {"post_generic": _MockPostGeneric}
        with patch("processors.base._POST_PROCESSOR_REGISTRY", registry):
            from processors.runner import run_postprocessors

            case = {
                "request_head": {},
                "request_body": {},
                "postprocessors": [{"name": "post_generic", "config": {}}],
            }
            response = self._make_mock_response()
            with pytest.raises(ProcessorError) as exc_info:
                run_postprocessors(case, response, {})

        assert exc_info.value.processor_name == "post_generic"
        assert "unexpected value error" in str(exc_info.value)

    def should_handle_empty_postprocessors_list(self):
        registry = {}
        with patch("processors.base._POST_PROCESSOR_REGISTRY", registry):
            from processors.runner import run_postprocessors

            case = {
                "request_head": {},
                "request_body": {},
                "postprocessors": [],
            }
            response = self._make_mock_response()
            results = run_postprocessors(case, response, {})

        assert results == []

    def should_handle_none_response(self):
        """When response is None, headers are empty and body is None."""
        registry = {"post_ok": _MockPostOk}
        with patch("processors.base._POST_PROCESSOR_REGISTRY", registry):
            from processors.runner import run_postprocessors

            case = {
                "request_head": {"Auth": "x"},
                "request_body": {"q": "t"},
                "postprocessors": [{"name": "post_ok", "config": {}}],
            }
            results = run_postprocessors(case, None, {})

        assert results == [{"name": "post_ok", "status": "ok"}]

    def should_handle_missing_request_head_and_body(self):
        """Case has no request_head/body keys."""
        registry = {"post_ok": _MockPostOk}
        with patch("processors.base._POST_PROCESSOR_REGISTRY", registry):
            from processors.runner import run_postprocessors

            case = {
                "postprocessors": [{"name": "post_ok", "config": {}}],
            }
            response = self._make_mock_response()
            results = run_postprocessors(case, response, {})

        assert results == [{"name": "post_ok", "status": "ok"}]
