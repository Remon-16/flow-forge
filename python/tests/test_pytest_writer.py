"""Tests for converter/pytest_writer.py — the pytest code generator."""

import json
import os
import re
import tempfile
from unittest.mock import MagicMock, patch

import pytest
import yaml

from converter.pytest_writer import (
    _generate_single_test,
    _generate_biz_flow_class,
    _generate_preprocessor_calls,
    _generate_postprocessor_calls,
    _sanitize_name,
    _indent_lines,
    yaml_to_pytest,
    excel_to_pytest,
)


class TestSanitizeName:
    def should_replace_special_chars(self):
        assert _sanitize_name("test/case:one") == "test_case_one"

    def should_keep_alphanumeric(self):
        assert _sanitize_name("valid_name_123") == "valid_name_123"


class TestIndentLines:
    def should_indent_non_empty_lines(self):
        text = "line1\n\nline2\n"
        result = _indent_lines(text, 4)
        lines = result.splitlines(True)
        assert lines[0] == "    line1\n"
        assert lines[1] == "\n"  # empty stays empty
        assert lines[2] == "    line2\n"

    def should_return_empty_for_empty_input(self):
        assert _indent_lines("", 4) == ""


class TestPreprocessorCalls:
    def should_return_empty_for_no_preprocessors(self):
        assert _generate_preprocessor_calls([]) == ""

    def should_generate_timestamp_call(self):
        result = _generate_preprocessor_calls([{"name": "timestamp", "config": {}}])
        assert "_apply_timestamp" in result

    def should_generate_hmac_sign_call(self):
        result = _generate_preprocessor_calls([{"name": "hmac-sign", "config": {"secret_env": "KEY"}}])
        assert "_apply_hmac_sign" in result
        assert '"secret_env"' in result

    def should_generate_print_demo_call(self):
        result = _generate_preprocessor_calls([{"name": "print-demo", "config": {"prefix": "[DEBUG]"}}])
        assert "_print_request" in result
        assert "[DEBUG]" in result

    def should_comment_unknown_processor(self):
        result = _generate_preprocessor_calls([{"name": "custom-auth", "config": {}}])
        assert "Custom processor" in result


class TestPostprocessorCalls:
    def should_return_empty_for_no_postprocessors(self):
        assert _generate_postprocessor_calls([]) == ""

    def should_generate_response_time_call(self):
        result = _generate_postprocessor_calls([{"name": "response-time", "config": {}}])
        assert "_log_response_metrics" in result

    def should_generate_hmac_verify_call(self):
        result = _generate_postprocessor_calls([{"name": "hmac-verify", "config": {"secret_env": "KEY"}}])
        assert "_verify_hmac" in result

    def should_generate_print_demo_post_call(self):
        result = _generate_postprocessor_calls([{"name": "print-demo-post", "config": {"prefix": "[POST]"}}])
        assert "_print_response" in result
        assert "[POST]" in result


class TestGenerateSingleTest:
    def should_contain_case_data_constant(self):
        case = {
            "test_id": "demo_001", "method": "GET", "url": "/api/status",
            "request_head": {}, "request_body": {}, "status_code": 200,
            "assert_dict": {"status": "ok"}, "assert_rules": [],
            "preprocessors": [], "postprocessors": [],
        }
        src = _generate_single_test(case, 0)
        assert "CASE_demo_001" in src
        assert "def test_demo_001(base_url)" in src
        assert "requests.request" in src

    def should_include_token_resolution_when_app_name_present(self):
        case = {
            "test_id": "auth_test", "method": "GET", "url": "/api/protected",
            "request_head": {}, "request_body": {}, "status_code": 200,
            "assert_dict": {}, "assert_rules": [],
            "preprocessors": [], "postprocessors": [],
            "app_name": "myApp",
        }
        src = _generate_single_test(case, 0)
        assert "_resolve_token" in src
        assert '"myApp"' in src

    def should_use_sanitized_test_id(self):
        case = {
            "test_id": "bad/name:test", "method": "GET", "url": "/",
            "request_head": {}, "request_body": {}, "status_code": 200,
            "assert_dict": {}, "assert_rules": [],
            "preprocessors": [], "postprocessors": [],
        }
        src = _generate_single_test(case, 0)
        assert "CASE_bad_name_test" in src
        assert "def test_bad_name_test" in src

    def should_include_assert_rules(self):
        case = {
            "test_id": "rules_test", "method": "GET", "url": "/api",
            "request_head": {}, "request_body": {}, "status_code": 200,
            "assert_dict": {},
            "assert_rules": ["items.length() > 0", "total == 100"],
            "preprocessors": [], "postprocessors": [],
        }
        src = _generate_single_test(case, 0)
        assert r'"items.length() > 0"' in src or "'items.length() > 0'" in src

    def should_generate_valid_python_syntax(self):
        """Generated test function must be valid Python."""
        case = {
            "test_id": "syntax_test", "method": "POST", "url": "/api/data",
            "request_head": {"Content-Type": "application/json"},
            "request_body": {"key": "value"},
            "status_code": 201,
            "assert_dict": {"status": "created"},
            "assert_rules": ["items.length() > 0"],
            "preprocessors": [{"name": "timestamp", "config": {}}],
            "postprocessors": [{"name": "response-time", "config": {}}],
        }
        src = _generate_single_test(case, 0)
        # Write to temp file and try to compile
        d = tempfile.mkdtemp()
        fp = os.path.join(d, "test_gen.py")
        with open(fp, "w", encoding="utf-8") as f:
            # Add minimal stubs so compile succeeds
            stubs = '''
def _resolve_url(u, b): return u
def _resolve_path(d, p): return None
def _assert_field(d, p, e): return True
def _assert_rules(d, r): return []
def _resolve_token(h, a): return h
def _apply_timestamp(h, c=None): pass
def _log_response_metrics(h, b, threshold=1048576): pass
'''
            f.write(stubs + "\n" + src)
        import py_compile
        py_compile.compile(fp, doraise=True)


class TestGenerateBizFlowClass:
    def should_create_class_with_setup_method(self):
        flow = {
            "sheet_name": "test_flow",
            "steps": [
                {"step_id": "s1", "method": "GET", "url": "/api/test",
                 "request_head": {}, "request_body": {}, "status_code": 200,
                 "assert_dict": {}, "assert_rules": [], "preprocessors": [], "postprocessors": []},
            ],
        }
        src = _generate_biz_flow_class(flow, 0)
        assert "class TestBizFlow_test_flow" in src
        assert "def setup_method(self)" in src
        assert "STEP_s1" in src

    def should_generate_multiple_steps(self):
        flow = {
            "sheet_name": "multi_step",
            "steps": [
                {"step_id": "login", "method": "POST", "url": "/auth/login",
                 "request_head": {}, "request_body": {}, "status_code": 200,
                 "assert_dict": {}, "assert_rules": [], "preprocessors": [], "postprocessors": []},
                {"step_id": "action", "method": "POST", "url": "/api/action",
                 "request_head": {}, "request_body": {}, "status_code": 201,
                 "assert_dict": {}, "assert_rules": [], "preprocessors": [], "postprocessors": []},
            ],
        }
        src = _generate_biz_flow_class(flow, 0)
        assert "STEP_login" in src
        assert "STEP_action" in src
        assert "def test_step_00_login" in src
        assert "def test_step_01_action" in src

    def should_include_inherit_handling(self):
        flow = {
            "sheet_name": "inherit_flow",
            "steps": [
                {"step_id": "get_token", "method": "POST", "url": "/auth/login",
                 "request_head": {}, "request_body": {}, "status_code": 200,
                 "assert_dict": {}, "assert_rules": [], "preprocessors": [], "postprocessors": []},
                {"step_id": "use_token", "method": "GET", "url": "/api/me",
                 "request_head": {}, "request_body": {}, "status_code": 200,
                 "assert_dict": {}, "assert_rules": [], "preprocessors": [], "postprocessors": [],
                 "inherit": {"token": "data.token"}},
            ],
        }
        src = _generate_biz_flow_class(flow, 0)
        assert "Inherit" in src
        assert "_resolve_path(self._flow_data" in src
        assert "data.token" in src

    def should_return_empty_for_no_steps(self):
        flow = {"sheet_name": "empty", "steps": []}
        assert _generate_biz_flow_class(flow, 0) == ""


class TestYamlToPytest:
    def should_generate_all_output_files(self):
        d = tempfile.mkdtemp()
        cases_dir = os.path.join(d, "cases", "single_cases")
        os.makedirs(cases_dir)
        case = {
            "test_id": "t1", "case_type": "single",
            "method": "GET", "url": "/api/test",
            "request_head": {}, "request_body": {}, "status_code": 200,
            "assert_dict": {}, "assert_rules": [],
            "preprocessors": [], "postprocessors": [],
        }
        with open(os.path.join(cases_dir, "t1.yaml"), "w") as f:
            yaml.safe_dump(case, f)

        out = os.path.join(d, "output")
        result = yaml_to_pytest(output_dir=out, single_cases_dir=cases_dir, config_dir=".")

        assert result["single_cases"] == 1
        assert result["biz_flows"] == 0
        assert os.path.isfile(os.path.join(out, "conftest.py"))
        assert os.path.isfile(os.path.join(out, "test_single_cases.py"))
        assert os.path.isfile(os.path.join(out, "_config.py"))
        assert os.path.isfile(os.path.join(out, "_ff_compat.py"))

    def should_raise_when_no_directory_provided(self):
        d = tempfile.mkdtemp()
        out = os.path.join(d, "output")
        with pytest.raises(ValueError, match="At least one"):
            yaml_to_pytest(output_dir=out, config_dir=".")

    def should_generate_biz_flow_tests(self):
        d = tempfile.mkdtemp()
        flows_dir = os.path.join(d, "cases", "biz_flows")
        os.makedirs(flows_dir)
        flow = {
            "sheet_name": "myflow", "case_type": "biz",
            "steps": [
                {"step_id": "s1", "method": "GET", "url": "/api/test",
                 "request_head": {}, "request_body": {}, "status_code": 200,
                 "assert_dict": {}, "assert_rules": [],
                 "preprocessors": [], "postprocessors": []},
            ],
        }
        with open(os.path.join(flows_dir, "myflow.yaml"), "w") as f:
            yaml.safe_dump(flow, f)

        out = os.path.join(d, "output")
        result = yaml_to_pytest(output_dir=out, biz_flows_dir=flows_dir, config_dir=".")
        assert result["biz_flows"] == 1
        assert os.path.isfile(os.path.join(out, "test_biz_flows.py"))

    def should_generate_env_config_files(self):
        d = tempfile.mkdtemp()
        # Create an env-*.yml file
        env_dir = os.path.join(d, "config")
        os.makedirs(env_dir)
        with open(os.path.join(env_dir, "env-test.yml"), "w") as f:
            yaml.safe_dump({"testApp": {"baseURL": "http://localhost:8000"}}, f)

        cases_dir = os.path.join(d, "cases", "single_cases")
        os.makedirs(cases_dir)
        case = {
            "test_id": "t1", "case_type": "single",
            "method": "GET", "url": "/api/test",
            "request_head": {}, "request_body": {}, "status_code": 200,
            "assert_dict": {}, "assert_rules": [],
            "preprocessors": [], "postprocessors": [],
        }
        with open(os.path.join(cases_dir, "t1.yaml"), "w") as f:
            yaml.safe_dump(case, f)

        out = os.path.join(d, "output")
        yaml_to_pytest(output_dir=out, single_cases_dir=cases_dir, config_dir=env_dir)

        # Should generate _env_test.py
        env_file = os.path.join(out, "_env_test.py")
        assert os.path.isfile(env_file)
        content = open(env_file, encoding="utf-8").read()
        assert "testApp" in content

        # _config.py should reference _env_test
        config_content = open(os.path.join(out, "_config.py"), encoding="utf-8").read()
        assert "_env_test" in config_content

    def should_handle_no_config_files(self):
        d = tempfile.mkdtemp()
        cases_dir = os.path.join(d, "cases", "single_cases")
        os.makedirs(cases_dir)
        case = {
            "test_id": "t1", "case_type": "single",
            "method": "GET", "url": "/api/test",
            "request_head": {}, "request_body": {}, "status_code": 200,
            "assert_dict": {}, "assert_rules": [],
            "preprocessors": [], "postprocessors": [],
        }
        with open(os.path.join(cases_dir, "t1.yaml"), "w") as f:
            yaml.safe_dump(case, f)

        out = os.path.join(d, "output")
        # Use a dir with no env-*.yml files
        empty_dir = os.path.join(d, "empty_config")
        os.makedirs(empty_dir)
        result = yaml_to_pytest(output_dir=out, single_cases_dir=cases_dir, config_dir=empty_dir)
        assert result["single_cases"] == 1


class TestExcelToPytest:
    def should_generate_from_mock_excel(self):
        """Generate pytest from a mocked Excel with single cases."""
        from converter.excel_reader import read_excel
        from converter.pytest_writer import _write_single_tests, _write_conftest, _write_ff_compat, _write_env_configs

        d = tempfile.mkdtemp()
        out = os.path.join(d, "output")
        os.makedirs(out)

        # Write support files first
        _write_conftest(out)
        _write_ff_compat(out)
        _write_env_configs(out, ".")
        _write_single_tests([{
            "test_id": "excel_test", "method": "POST", "url": "/api/data",
            "request_head": {}, "request_body": {"k": "v"},
            "status_code": 200,
            "assert_dict": {"status": "ok"}, "assert_rules": [],
            "preprocessors": [], "postprocessors": [],
        }], out)

        import py_compile
        test_file = os.path.join(out, "test_single_cases.py")
        py_compile.compile(test_file, doraise=True)
        content = open(test_file, encoding="utf-8").read()
        assert "excel_test" in content


class TestCompatModule:
    def should_contain_minimal_stubs(self):
        from converter.pytest_writer import _FF_COMPAT_TEMPLATE
        assert "class PreProcessor" in _FF_COMPAT_TEMPLATE
        assert "class PostProcessor" in _FF_COMPAT_TEMPLATE
        assert "class ProcessorError" in _FF_COMPAT_TEMPLATE
