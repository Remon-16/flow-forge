"""Tests for built-in processors in processors/builtin/."""

import hashlib
import hmac
import json
import logging
import os
import re
import uuid
from unittest.mock import MagicMock, patch

import pytest

from processors.base import ProcessorError


# ============================================================================
# TimestampPreProcessor
# ============================================================================

class TestTimestampPreProcessorTest:

    def should_add_timestamp_and_request_id_headers(self):
        from processors.builtin.pre.timestamp_sign_pre import TimestampPreProcessor

        proc = TimestampPreProcessor()
        headers, body = proc.process({}, {}, {}, {})

        assert "X-Timestamp" in headers
        assert "X-Request-Id" in headers
        assert body == {}

    def should_use_custom_header_names(self):
        from processors.builtin.pre.timestamp_sign_pre import TimestampPreProcessor

        proc = TimestampPreProcessor()
        headers, body = proc.process(
            {}, {},
            {"header_timestamp": "X-My-TS", "header_request_id": "X-My-RID"},
            {},
        )

        assert "X-My-TS" in headers
        assert "X-My-RID" in headers
        assert "X-Timestamp" not in headers
        assert "X-Request-Id" not in headers

    def should_pass_through_body_unchanged(self):
        from processors.builtin.pre.timestamp_sign_pre import TimestampPreProcessor

        proc = TimestampPreProcessor()
        original_body = {"key": "value", "nested": {"deep": True}}
        headers, body = proc.process({}, dict(original_body), {}, {})

        assert body == original_body

    def should_produce_valid_iso8601_timestamp(self):
        from processors.builtin.pre.timestamp_sign_pre import TimestampPreProcessor

        proc = TimestampPreProcessor()
        headers, _ = proc.process({}, {}, {}, {})

        ts = headers["X-Timestamp"]
        # ISO 8601 UTC: e.g. 2026-06-30T12:34:56.789123+00:00
        # Must end with +00:00 or Z
        assert ts.endswith("+00:00") or ts.endswith("Z")
        assert "T" in ts

    def should_produce_valid_uuid4_request_id(self):
        from processors.builtin.pre.timestamp_sign_pre import TimestampPreProcessor

        proc = TimestampPreProcessor()
        headers, _ = proc.process({}, {}, {}, {})

        req_id = headers["X-Request-Id"]
        # Must be a valid UUID
        uuid.UUID(req_id)
        # UUID v4 has version nibble = 4
        assert req_id[14] == "4"


# ============================================================================
# PrintDemoPreProcessor
# ============================================================================

class TestPrintDemoPreProcessorTest:

    def should_log_request_summary_at_info_level(self, caplog):
        from processors.builtin.pre.print_demo_pre import PrintDemoPreProcessor

        proc = PrintDemoPreProcessor()
        with caplog.at_level(logging.INFO):
            proc.process(
                {"Content-Type": "application/json"},
                {"name": "test"},
                {},
                {},
            )

        assert any("Content-Type" in m for m in caplog.messages)
        assert any("name" in m for m in caplog.messages)

    def should_pass_through_headers_and_body_unchanged(self):
        from processors.builtin.pre.print_demo_pre import PrintDemoPreProcessor

        proc = PrintDemoPreProcessor()
        original_headers = {"Auth": "secret"}
        original_body = {"data": "important"}

        headers, body = proc.process(
            dict(original_headers), dict(original_body), {}, {}
        )

        assert headers == original_headers
        assert body == original_body

    def should_use_custom_log_prefix(self, caplog):
        from processors.builtin.pre.print_demo_pre import PrintDemoPreProcessor

        proc = PrintDemoPreProcessor()
        with caplog.at_level(logging.INFO):
            proc.process({}, {}, {"prefix": "[CustomPrefix]"}, {})

        assert any("[CustomPrefix]" in m for m in caplog.messages)


# ============================================================================
# PrintDemoPostProcessor
# ============================================================================

class TestPrintDemoPostProcessorTest:

    def should_log_response_summary_at_info_level(self, caplog):
        from processors.builtin.post.print_demo_post import PrintDemoPostProcessor

        proc = PrintDemoPostProcessor()
        with caplog.at_level(logging.INFO):
            proc.process(
                {}, {},
                {"Content-Type": "application/json"},
                {"result": "ok"},
                {}, {},
            )

        assert any("Content-Type" in m for m in caplog.messages)

    def should_use_custom_log_prefix(self, caplog):
        from processors.builtin.post.print_demo_post import PrintDemoPostProcessor

        proc = PrintDemoPostProcessor()
        with caplog.at_level(logging.INFO):
            proc.process({}, {}, {}, {}, {"prefix": "[PostCustom]"}, {})

        assert any("[PostCustom]" in m for m in caplog.messages)

    def should_handle_none_response_body(self, caplog):
        from processors.builtin.post.print_demo_post import PrintDemoPostProcessor

        proc = PrintDemoPostProcessor()
        with caplog.at_level(logging.INFO):
            # Should not raise
            proc.process({}, {}, {}, None, {}, {})

        assert any("None" in m for m in caplog.messages)


# ============================================================================
# ResponseTimePostProcessor
# ============================================================================

class TestResponseTimePostProcessorTest:

    def should_log_content_length(self, caplog):
        from processors.builtin.post.response_time_post import ResponseTimePostProcessor

        proc = ResponseTimePostProcessor()
        with caplog.at_level(logging.INFO):
            proc.process(
                {}, {},
                {"Content-Length": "512"},
                {"data": "ok"},
                {}, {},
            )

        assert any("512" in m for m in caplog.messages)

    def should_warn_when_body_exceeds_threshold(self, caplog):
        from processors.builtin.post.response_time_post import ResponseTimePostProcessor

        proc = ResponseTimePostProcessor()
        with caplog.at_level(logging.WARNING):
            proc.process(
                {}, {},
                {"Content-Length": "2000000"},  # 2 MB, threshold 1 MB
                {}, {}, {},
            )

        assert any("exceeds threshold" in m for m in caplog.messages)

    def should_compute_length_from_body_when_no_header(self, caplog):
        from processors.builtin.post.response_time_post import ResponseTimePostProcessor

        proc = ResponseTimePostProcessor()
        body = {"data": "x" * 100}
        with caplog.at_level(logging.INFO):
            proc.process({}, {}, {}, body, {}, {})

        assert any("bytes" in m for m in caplog.messages)

    def should_handle_non_json_response(self, caplog):
        from processors.builtin.post.response_time_post import ResponseTimePostProcessor

        proc = ResponseTimePostProcessor()
        with caplog.at_level(logging.INFO):
            # plain text body
            proc.process({}, {}, {}, "plain text response", {}, {})

        assert any("bytes" in m for m in caplog.messages)

    def should_handle_missing_content_type_header(self, caplog):
        from processors.builtin.post.response_time_post import ResponseTimePostProcessor

        proc = ResponseTimePostProcessor()
        with caplog.at_level(logging.INFO):
            proc.process({}, {}, {}, None, {}, {})

        assert any("unknown" in m.lower() for m in caplog.messages)


# ============================================================================
# HmacVerifyPostProcessor
# ============================================================================

class TestHmacVerifyPostProcessorTest:

    def _compute_signature(self, secret, body_str):
        payload = body_str
        return hmac.new(
            secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def should_pass_when_signature_matches(self):
        from processors.builtin.post.hmac_verify_post import HmacVerifyPostProcessor

        secret = "test-secret"
        body = {"result": "success"}
        body_str = json.dumps(body, ensure_ascii=False, sort_keys=True)
        sig = self._compute_signature(secret, body_str)

        proc = HmacVerifyPostProcessor()
        with patch.dict(os.environ, {"MY_SECRET": secret}):
            # Should not raise
            proc.process(
                {}, {},
                {"X-Signature": sig},
                body,
                {"secret_env": "MY_SECRET"},
                {},
            )

    def should_raise_processor_error_when_signature_mismatch(self):
        from processors.builtin.post.hmac_verify_post import HmacVerifyPostProcessor

        secret = "test-secret"
        body = {"result": "success"}
        body_str = json.dumps(body, ensure_ascii=False, sort_keys=True)
        correct_sig = self._compute_signature(secret, body_str)
        wrong_sig = correct_sig + "tampered"

        proc = HmacVerifyPostProcessor()
        with patch.dict(os.environ, {"MY_SECRET": secret}):
            with pytest.raises(ProcessorError, match="mismatch"):
                proc.process(
                    {}, {},
                    {"X-Signature": wrong_sig},
                    body,
                    {"secret_env": "MY_SECRET"},
                    {},
                )

    def should_raise_processor_error_when_header_missing(self):
        from processors.builtin.post.hmac_verify_post import HmacVerifyPostProcessor

        proc = HmacVerifyPostProcessor()
        with patch.dict(os.environ, {"MY_SECRET": "secret"}):
            with pytest.raises(ProcessorError, match="not found"):
                proc.process(
                    {}, {},
                    {},  # No signature header
                    {"data": "test"},
                    {"secret_env": "MY_SECRET"},
                    {},
                )

    def should_raise_when_secret_env_empty(self):
        """密钥为空时应抛出 ProcessorError，判定用例失败。
           When secret is empty, raise ProcessorError to fail the test case."""
        from processors.builtin.post.hmac_verify_post import HmacVerifyPostProcessor

        proc = HmacVerifyPostProcessor()
        with pytest.raises(ProcessorError, match="empty or not set"):
            proc.process(
                {}, {}, {}, {"data": "test"},
                {"secret_env": "EMPTY_SECRET"}, {},
            )

    def should_use_custom_header_name(self):
        from processors.builtin.post.hmac_verify_post import HmacVerifyPostProcessor

        secret = "test-secret"
        body_str = ""
        sig = self._compute_signature(secret, body_str)

        proc = HmacVerifyPostProcessor()
        with patch.dict(os.environ, {"SIGN_KEY": secret}):
            proc.process(
                {}, {},
                {"X-My-Sig": sig},
                None,
                {"secret_env": "SIGN_KEY", "header_name": "X-My-Sig"},
                {},
            )

    def should_use_global_processor_config(self):
        from processors.builtin.post.hmac_verify_post import HmacVerifyPostProcessor

        secret = "test-secret"
        body_str = ""
        sig = self._compute_signature(secret, body_str)

        proc = HmacVerifyPostProcessor()
        global_cfg = {
            "processor_configs": {
                "hmac-verify": {
                    "secret_env": "GLOBAL_SECRET",
                    "header_name": "X-Global-Sig",
                },
            },
        }
        with patch.dict(os.environ, {"GLOBAL_SECRET": secret}):
            proc.process(
                {}, {},
                {"X-Global-Sig": sig},
                None,
                {},  # no case-level config, fallback to global
                global_cfg,
            )

    def should_handle_plain_text_response_body(self):
        from processors.builtin.post.hmac_verify_post import HmacVerifyPostProcessor

        secret = "test-secret"
        body_str = "plain text body"
        sig = self._compute_signature(secret, body_str)

        proc = HmacVerifyPostProcessor()
        with patch.dict(os.environ, {"MY_SECRET": secret}):
            proc.process(
                {}, {},
                {"X-Signature": sig},
                body_str,
                {"secret_env": "MY_SECRET"},
                {},
            )


# ============================================================================
# PathParamRestorePreProcessor
# ============================================================================

class TestPathParamRestorePreProcessorTest:

    def should_restore_all_cleared_fields_to_body(self):
        from processors.builtin.pre.path_param_restore_pre import PathParamRestorePreProcessor

        proc = PathParamRestorePreProcessor()
        headers, body = proc.process(
            {"Content-Type": "application/json"},
            {"name": "Store"},
            {"fields": "all"},
            {"_cleared_path_params": {"id": "12345"}},
        )

        assert body == {"name": "Store", "id": "12345"}
        # headers unchanged
        assert headers == {"Content-Type": "application/json"}

    def should_restore_specific_fields_to_body(self):
        from processors.builtin.pre.path_param_restore_pre import PathParamRestorePreProcessor

        proc = PathParamRestorePreProcessor()
        headers, body = proc.process(
            {},
            {"name": "Store"},
            {"fields": ["id"]},
            {"_cleared_path_params": {"id": "12345", "uid": "67890"}},
        )

        assert body == {"name": "Store", "id": "12345"}
        assert "uid" not in body

    def should_do_nothing_when_no_cleared_params(self):
        from processors.builtin.pre.path_param_restore_pre import PathParamRestorePreProcessor

        proc = PathParamRestorePreProcessor()
        headers, body = proc.process(
            {}, {"original": True}, {"fields": "all"}, {},
        )

        assert body == {"original": True}

    def should_do_nothing_when_cleared_params_is_empty_dict(self):
        from processors.builtin.pre.path_param_restore_pre import PathParamRestorePreProcessor

        proc = PathParamRestorePreProcessor()
        headers, body = proc.process(
            {}, {"original": True}, {"fields": "all"},
            {"_cleared_path_params": {}},
        )

        assert body == {"original": True}

    def should_pass_through_headers_unchanged(self):
        from processors.builtin.pre.path_param_restore_pre import PathParamRestorePreProcessor

        proc = PathParamRestorePreProcessor()
        original_headers = {"X-Custom": "val", "Authorization": "Bearer token"}
        headers, body = proc.process(
            dict(original_headers), {},
            {"fields": "all"},
            {"_cleared_path_params": {"a": "1"}},
        )

        assert headers == original_headers

    def should_handle_non_list_fields_config(self, caplog):
        from processors.builtin.pre.path_param_restore_pre import PathParamRestorePreProcessor

        proc = PathParamRestorePreProcessor()
        with caplog.at_level(logging.WARNING):
            headers, body = proc.process(
                {}, {},
                {"fields": "invalid-value"},  # not "all" and not a list
                {"_cleared_path_params": {"id": "1"}},
            )

        assert body == {}  # nothing restored
        assert any("Invalid" in m for m in caplog.messages)


# ============================================================================
# Multi-processor chain tests
# ============================================================================

class TestMultiProcessorChainTest:

    @staticmethod
    def _run_chain(registry, preprocessors, headers, body, case_config=None,
                   global_config=None):
        """Helper: run preprocessors via the runner with a given registry."""
        case_config = case_config or {}
        global_config = global_config or {}
        with patch("processors.base._PRE_PROCESSOR_REGISTRY", registry):
            from processors.runner import run_preprocessors
            case = {
                "request_head": headers,
                "request_body": body,
                "preprocessors": preprocessors,
            }
            return run_preprocessors(case, global_config)

    def should_run_multiple_preprocessors_in_order(self):
        call_order = []

        class PreA:
            name = "pre_a"
            def can_process(self, case): return True
            def process(self, headers, body, case_config, global_config):
                call_order.append("a")
                return headers, body

        class PreB:
            name = "pre_b"
            def can_process(self, case): return True
            def process(self, headers, body, case_config, global_config):
                call_order.append("b")
                return headers, body

        registry = {"pre_a": PreA, "pre_b": PreB}
        self._run_chain(
            registry,
            [{"name": "pre_a"}, {"name": "pre_b"}],
            {}, {},
        )
        assert call_order == ["a", "b"]

    def should_run_multiple_postprocessors_in_order(self):
        call_order = []

        class PostA:
            name = "post_a"
            def process(self, req_h, req_b, resp_h, resp_b, case_cfg, global_cfg):
                call_order.append("a")

        class PostB:
            name = "post_b"
            def process(self, req_h, req_b, resp_h, resp_b, case_cfg, global_cfg):
                call_order.append("b")

        with patch("processors.base._POST_PROCESSOR_REGISTRY", {"post_a": PostA, "post_b": PostB}):
            from processors.runner import run_postprocessors
            case = {
                "request_head": {},
                "request_body": {},
                "postprocessors": [
                    {"name": "post_a"},
                    {"name": "post_b"},
                ],
            }
            resp = MagicMock()
            resp.headers = {}
            resp.json.return_value = {}
            run_postprocessors(case, resp, {})

        assert call_order == ["a", "b"]

    def should_run_both_pre_and_post(self):
        """Integration: pre + post in the same chain."""
        call_order = []

        class ChainPre:
            name = "chain_pre"
            def can_process(self, case): return True
            def process(self, headers, body, case_config, global_config):
                call_order.append("pre")
                headers["X-Modified"] = "1"
                return headers, body

        class ChainPost:
            name = "chain_post"
            def process(self, req_h, req_b, resp_h, resp_b, case_cfg, global_cfg):
                call_order.append("post")
                assert req_h.get("X-Modified") == "1"  # pre's change visible

        with patch("processors.base._PRE_PROCESSOR_REGISTRY", {"chain_pre": ChainPre}), \
             patch("processors.base._POST_PROCESSOR_REGISTRY", {"chain_post": ChainPost}):
            from processors.runner import run_preprocessors, run_postprocessors

            case_pre = {
                "request_head": {},
                "request_body": {},
                "preprocessors": [{"name": "chain_pre"}],
            }
            headers, body, results = run_preprocessors(case_pre, {})
            assert headers["X-Modified"] == "1"

            resp = MagicMock()
            resp.headers = {}
            resp.json.return_value = {}
            case_post = {
                "request_head": headers,
                "request_body": body,
                "postprocessors": [{"name": "chain_post"}],
            }
            run_postprocessors(case_post, resp, {})

        assert call_order == ["pre", "post"]

    def should_stop_on_first_preprocessor_error(self):
        call_order = []

        class PreOk:
            name = "pre_ok"
            def can_process(self, case): return True
            def process(self, headers, body, case_config, global_config):
                call_order.append("ok")
                return headers, body

        class PreFail:
            name = "pre_fail"
            def can_process(self, case): return True
            def process(self, headers, body, case_config, global_config):
                call_order.append("fail")
                raise ProcessorError("forced error", processor_name="pre_fail")

        class PreNeverCalled:
            name = "pre_never"
            def can_process(self, case): return True
            def process(self, headers, body, case_config, global_config):
                call_order.append("never")
                return headers, body

        registry = {"pre_ok": PreOk, "pre_fail": PreFail, "pre_never": PreNeverCalled}
        with pytest.raises(ProcessorError, match="forced error"):
            self._run_chain(
                registry,
                [{"name": "pre_ok"}, {"name": "pre_fail"}, {"name": "pre_never"}],
                {}, {},
            )

        assert call_order == ["ok", "fail"]
        assert "never" not in call_order
