"""Tests for URL path parameter resolution — #{varName} and {varName} formats."""

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

from executor.base import BaseExecutor


class TestResolveUrlPlaceholdersTest:

    # --- #{varName} hash format ---

    def should_resolve_hash_placeholder_from_body(self):
        url, body, cleared = BaseExecutor._resolve_url_placeholders(
            "/api/users/#{userId}", {"userId": "123"}
        )
        assert url == "/api/users/123"
        assert "userId" not in body
        assert cleared == {"userId": "123"}

    def should_leave_hash_unresolved_when_key_not_in_body(self):
        url, body, cleared = BaseExecutor._resolve_url_placeholders(
            "/api/users/#{unknown}", {"other": "val"}
        )
        assert url == "/api/users/#{unknown}"
        assert body == {"other": "val"}
        assert cleared == {}

    # --- {varName} curly format ---

    def should_resolve_curly_placeholder_from_body(self):
        url, body, cleared = BaseExecutor._resolve_url_placeholders(
            "/api/stores/{id}", {"id": "456", "name": "Store"}
        )
        assert url == "/api/stores/456"
        assert "id" not in body
        assert body == {"name": "Store"}
        assert cleared == {"id": "456"}

    def should_leave_curly_unresolved_when_key_not_in_body(self):
        url, body, cleared = BaseExecutor._resolve_url_placeholders(
            "/api/stores/{missing}", {"other": "x"}
        )
        assert url == "/api/stores/{missing}"
        assert body == {"other": "x"}
        assert cleared == {}

    # --- mixed formats ---

    def should_handle_mixed_placeholders(self):
        url, body, cleared = BaseExecutor._resolve_url_placeholders(
            "/api/#{a}/{b}", {"a": "1", "b": "2"}
        )
        assert url == "/api/1/2"
        assert "a" not in body
        assert "b" not in body
        assert cleared == {"a": "1", "b": "2"}

    def should_resolve_same_key_in_both_formats(self):
        url, body, cleared = BaseExecutor._resolve_url_placeholders(
            "/api/#{uid}/items/{uid}", {"uid": "42"}
        )
        assert url == "/api/42/items/42"
        assert "uid" not in body
        assert cleared == {"uid": "42"}

    # --- no placeholders ---

    def should_handle_url_without_placeholders(self):
        url, body, cleared = BaseExecutor._resolve_url_placeholders(
            "/api/static/path", {"a": "1"}
        )
        assert url == "/api/static/path"
        assert body == {"a": "1"}
        assert cleared == {}

    def should_handle_empty_body(self):
        url, body, cleared = BaseExecutor._resolve_url_placeholders(
            "/api/users/#{id}", {}
        )
        assert url == "/api/users/#{id}"
        assert body == {}
        assert cleared == {}

    def should_handle_special_characters_in_value(self):
        url, body, cleared = BaseExecutor._resolve_url_placeholders(
            "/api/search/{query}", {"query": "hello world & more"}
        )
        assert url == "/api/search/hello world & more"
        assert "query" not in body
        assert cleared == {"query": "hello world & more"}

    # --- caller's dict is not mutated ---

    def should_not_mutate_caller_dict(self):
        original = {"userId": "999"}
        url, body, cleared = BaseExecutor._resolve_url_placeholders(
            "/api/users/#{userId}", original
        )
        assert original == {"userId": "999"}  # caller's dict unchanged

    # --- query string ---

    def should_resolve_placeholder_in_query_string(self):
        url, body, cleared = BaseExecutor._resolve_url_placeholders(
            "/api/users?filter=#{name}", {"name": "bob"}
        )
        assert url == "/api/users?filter=bob"
        assert "name" not in body
        assert cleared == {"name": "bob"}


class TestClearedPathParamsTest:

    def should_return_triple_from_resolve_url_placeholders(self):
        result = BaseExecutor._resolve_url_placeholders("/api/test", {"a": "1"})
        assert isinstance(result, tuple)
        assert len(result) == 3

    def should_record_single_cleared_field(self):
        url, body, cleared = BaseExecutor._resolve_url_placeholders(
            "/api/{id}", {"id": "12345"}
        )
        assert cleared == {"id": "12345"}

    def should_record_all_cleared_fields(self):
        url, body, cleared = BaseExecutor._resolve_url_placeholders(
            "/api/#{a}/#{b}/{c}", {"a": "1", "b": "2", "c": "3"}
        )
        assert cleared == {"a": "1", "b": "2", "c": "3"}

    def should_return_empty_cleared_params_when_no_body_keys_match(self):
        url, body, cleared = BaseExecutor._resolve_url_placeholders(
            "/api/{missing}", {"other": "x"}
        )
        assert cleared == {}

    def should_return_empty_cleared_params_for_url_without_placeholders(self):
        url, body, cleared = BaseExecutor._resolve_url_placeholders(
            "/api/static", {"a": "1"}
        )
        assert cleared == {}


class TestThreadSafetyTest:

    def should_isolate_cleared_params_per_thread(self):
        """Each thread must see only its own _cleared_path_params."""
        captured = {}

        class SpyPre:
            name = "spy"

            def can_process(self, case):
                return True

            def process(self, headers, body, case_config, global_config):
                test_id = case_config.get("test_id", "unknown")
                captured[test_id] = global_config.get("_cleared_path_params", {})
                return headers, body

        cases = [
            {
                "test_id": "A",
                "method": "GET",
                "url": "/api/#{uid}",
                "request_head": {},
                "request_body": {"uid": "A-val"},
                "preprocessors": [{"name": "spy", "config": {"test_id": "A"}}],
            },
            {
                "test_id": "B",
                "method": "GET",
                "url": "/api/{id}",
                "request_head": {},
                "request_body": {"id": "B-val"},
                "preprocessors": [{"name": "spy", "config": {"test_id": "B"}}],
            },
            {
                "test_id": "C",
                "method": "GET",
                "url": "/api/static",
                "request_head": {},
                "request_body": {"x": "y"},
                "preprocessors": [{"name": "spy", "config": {"test_id": "C"}}],
            },
        ]

        with patch("processors.base._PRE_PROCESSOR_REGISTRY", {"spy": SpyPre}), \
             patch("processors.loader.discover_processors", lambda: None), \
             patch("config.config_manager.get_all", return_value={"global_cfg": True}):
            from processors.runner import run_preprocessors

            def worker(case):
                headers = dict(case.get("request_head") or {})
                body = dict(case.get("request_body") or {})
                url, body, cleared_params = BaseExecutor._resolve_url_placeholders(
                    case["url"], body
                )
                global_config = {"global_cfg": True}
                if cleared_params:
                    config_for_proc = dict(global_config)
                    config_for_proc["_cleared_path_params"] = cleared_params
                else:
                    config_for_proc = global_config
                case_to_pass = {
                    "request_head": headers,
                    "request_body": body,
                    "preprocessors": case["preprocessors"],
                }
                run_preprocessors(case_to_pass, config_for_proc)

            with ThreadPoolExecutor(max_workers=3) as pool:
                futures = [pool.submit(worker, c) for c in cases]
                for f in futures:
                    f.result()

        # Thread A should see only its own cleared params
        assert captured["A"] == {"uid": "A-val"}
        # Thread B should see only its own cleared params
        assert captured["B"] == {"id": "B-val"}
        # Thread C should see empty cleared params (no placeholders)
        assert captured["C"] == {}

    def should_not_mutate_original_global_config(self):
        """The original global_config dict must not get _cleared_path_params."""
        original = {"processor_configs": {"some": "cfg"}}
        cleared = {"id": "12345"}

        # Simulate the shallow-copy + inject pattern used in executors
        config_for_proc = dict(original)
        config_for_proc["_cleared_path_params"] = cleared

        # original must be clean
        assert "_cleared_path_params" not in original
        # the copy has the injection
        assert config_for_proc["_cleared_path_params"] == cleared
        assert config_for_proc["processor_configs"] == {"some": "cfg"}
