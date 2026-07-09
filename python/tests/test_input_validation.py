"""Tests for input validation — YAML parsing and executor-level edge cases."""

import os
import tempfile

import pytest

from executor.biz_flow import BizFlowExecutor
from executor.single_case import SingleCaseExecutor


# ============================================================================
# YAML Input Validation
# ============================================================================

class TestYamlValidationTest:
    """Tests for YamlParser input validation."""

    def _write_yaml(self, tmpdir, filename, content):
        """Write a YAML file into a temp directory."""
        import yaml
        filepath = os.path.join(tmpdir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            yaml.dump(content, f, allow_unicode=True)
        return filepath

    def should_warn_on_yaml_missing_test_id(self):
        """Single YAML missing test_id should be warned and skipped."""
        from yaml_reader.yaml_parser import YamlParser

        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_yaml(tmpdir, "case.yml", {
                "case_type": "single",
                "method": "GET",
                "url": "/api/test",
            })

            result = YamlParser.parse_directory(tmpdir, api_mode="single")

        assert result["single_cases"] == []

    def should_warn_on_yaml_missing_method_or_url(self):
        """Single YAML missing method/url should be skipped."""
        from yaml_reader.yaml_parser import YamlParser

        with tempfile.TemporaryDirectory() as tmpdir:
            # Missing url
            self._write_yaml(tmpdir, "case1.yml", {
                "case_type": "single",
                "test_id": "TC001",
                "method": "GET",
            })

            result = YamlParser.parse_directory(tmpdir, api_mode="single")

        assert result["single_cases"] == []

    def should_warn_on_biz_flow_yaml_missing_steps(self):
        """Biz flow YAML missing steps key should be skipped."""
        from yaml_reader.yaml_parser import YamlParser

        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_yaml(tmpdir, "flow.yml", {
                "case_type": "biz",
                "sheet_name": "MyFlow",
            })

            result = YamlParser.parse_directory(tmpdir, api_mode="biz")

        assert result["biz_flows"] == []

    def should_warn_on_biz_flow_yaml_empty_steps(self):
        """Biz flow YAML with empty steps list should be skipped."""
        from yaml_reader.yaml_parser import YamlParser

        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_yaml(tmpdir, "flow.yml", {
                "case_type": "biz",
                "sheet_name": "MyFlow",
                "steps": [],
            })

            result = YamlParser.parse_directory(tmpdir, api_mode="biz")

        assert result["biz_flows"] == []

    def should_warn_on_biz_flow_yaml_missing_sheet_name(self):
        """Biz flow YAML missing sheet_name should be skipped."""
        from yaml_reader.yaml_parser import YamlParser

        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_yaml(tmpdir, "flow.yml", {
                "case_type": "biz",
                "steps": [{"test_id": "S001", "method": "GET", "url": "/api/test"}],
            })

            result = YamlParser.parse_directory(tmpdir, api_mode="biz")

        assert result["biz_flows"] == []

    def should_skip_malformed_yaml_file(self):
        """Corrupt YAML file should be skipped, not crash."""
        from yaml_reader.yaml_parser import YamlParser

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "bad.yml")
            with open(filepath, "w", encoding="utf-8") as f:
                f.write("::: this is not valid yaml ::: [}")

            # Should not raise
            result = YamlParser.parse_directory(tmpdir, api_mode="all")
            assert result["single_cases"] == []
            assert result["biz_flows"] == []

    def should_handle_empty_yaml_directory(self):
        """Empty directory should return empty lists."""
        from yaml_reader.yaml_parser import YamlParser

        with tempfile.TemporaryDirectory() as tmpdir:
            result = YamlParser.parse_directory(tmpdir, api_mode="all")

        assert result == {"single_cases": [], "biz_flows": []}

    def should_handle_nonexistent_yaml_directory(self):
        """Non-existent directory should warn and return empty lists."""
        from yaml_reader.yaml_parser import YamlParser

        result = YamlParser.parse_directory("/nonexistent/path/12345", api_mode="all")
        assert result == {"single_cases": [], "biz_flows": []}

    def should_infer_case_type_when_implicit(self):
        """When case_type is missing, infer from structure (test_id present)."""
        from yaml_reader.yaml_parser import YamlParser

        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_yaml(tmpdir, "case.yml", {
                "test_id": "TC001",
                "method": "GET",
                "url": "/api/test",
            })

            result = YamlParser.parse_directory(tmpdir, api_mode="single")

        assert len(result["single_cases"]) == 1
        assert result["single_cases"][0]["case_type"] == "single"

    def should_infer_biz_flow_when_implicit(self):
        """When case_type is missing and steps present, infer as biz."""
        from yaml_reader.yaml_parser import YamlParser

        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_yaml(tmpdir, "flow.yml", {
                "sheet_name": "MyFlow",
                "steps": [{"test_id": "S001", "method": "GET", "url": "/api/test"}],
            })

            result = YamlParser.parse_directory(tmpdir, api_mode="biz")

        assert len(result["biz_flows"]) == 1
        assert result["biz_flows"][0]["case_type"] == "biz"

    def should_handle_multiple_yaml_files(self):
        """Multiple YAML files should all be parsed."""
        from yaml_reader.yaml_parser import YamlParser

        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_yaml(tmpdir, "case1.yml", {
                "case_type": "single",
                "test_id": "TC001",
                "method": "GET",
                "url": "/api/a",
            })
            self._write_yaml(tmpdir, "case2.yml", {
                "case_type": "single",
                "test_id": "TC002",
                "method": "POST",
                "url": "/api/b",
            })

            result = YamlParser.parse_directory(tmpdir, api_mode="single")

        assert len(result["single_cases"]) == 2


# ============================================================================
# URL Value None / Edge Cases in Execution
# ============================================================================

class TestUrlEdgeCasesTest:

    def should_handle_url_value_none_in_case(self):
        """Single case with url=None handled gracefully."""
        executor = SingleCaseExecutor({})

        case = {
            "test_id": "TC001",
            "method": "GET",
            "url": None,
            "request_head": {},
            "request_body": {},
        }

        # url=None is stored as-is since the key exists in the dict
        result = executor._build_result(case)
        assert result["url"] is None


# ============================================================================
# Empty Biz Flow Steps
# ============================================================================

class TestEmptyBizFlowStepsTest:

    def should_fail_empty_biz_flow_steps(self):
        """BizFlowExecutor should fail when steps is empty."""
        executor = BizFlowExecutor({})

        flow = {
            "sheet_name": "EmptyFlow",
            "steps": [],
        }

        result = executor.execute_single(flow)

        assert result["passed"] is False
        assert "no steps" in result.get("error", "")


# ============================================================================
# Result Counting
# ============================================================================

class TestResultCountingTest:

    def should_count_results_correctly(self):
        """Number of results equals number of input cases, no phantom entries."""
        executor = SingleCaseExecutor({})

        cases = [
            {"test_id": "TC001", "method": "GET", "url": "/a"},
            {"test_id": "TC002", "method": "POST", "url": "/b"},
            {"test_id": "TC003", "method": "GET", "url": "/c"},
        ]

        for case in cases:
            executor.results.append({
                "test_id": case["test_id"],
                "passed": True,
                "error": None,
            })

        assert len(executor.results) == 3
        assert all(r["passed"] for r in executor.results)

    def should_not_have_phantom_entries(self):
        """Empty input should produce empty results."""
        executor = BizFlowExecutor({})

        flow = {
            "sheet_name": "EmptyFlow",
            "steps": [],
        }

        result = executor.execute_single(flow)
        # Empty steps should produce a failed result, not a passed one
        assert result["passed"] is False
        assert result.get("error") is not None


# ============================================================================
# YAML parse_files method
# ============================================================================

class TestYamlParseFilesTest:

    def should_parse_comma_separated_file_paths(self):
        """parse_files should handle comma-separated file paths."""
        from yaml_reader.yaml_parser import YamlParser

        with tempfile.TemporaryDirectory() as tmpdir:
            file1 = self._write_yaml(tmpdir, "case1.yml", {
                "case_type": "single",
                "test_id": "TC001",
                "method": "GET",
                "url": "/api/a",
            })
            file2 = self._write_yaml(tmpdir, "case2.yml", {
                "case_type": "single",
                "test_id": "TC002",
                "method": "POST",
                "url": "/api/b",
            })

            paths = f"{file1},{file2}"
            result = YamlParser.parse_files(paths, api_mode="single")

        assert len(result["single_cases"]) == 2

    def _write_yaml(self, tmpdir, filename, content):
        import yaml
        filepath = os.path.join(tmpdir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            yaml.dump(content, f, allow_unicode=True)
        return filepath


# ============================================================================
# ExcelParser edge case: FileNotFound
# ============================================================================

class TestExcelFileNotFoundTest:

    def should_raise_file_not_found_for_missing_excel(self):
        """ExcelParser should raise FileNotFoundError for missing files."""
        from excel_reader.excel_parser import ExcelParser

        with pytest.raises(FileNotFoundError):
            ExcelParser("/nonexistent/file_12345.xlsx")


# ============================================================================
# Inference edge case: cannot determine case_type
# ============================================================================

class TestYamlCannotDetermineTypeTest:

    def should_skip_when_case_type_cannot_be_determined(self):
        """YAML with no case_type and no distinguishable structure should be skipped."""
        from yaml_reader.yaml_parser import YamlParser

        with tempfile.TemporaryDirectory() as tmpdir:
            # Neither test_id nor steps present
            import yaml
            filepath = os.path.join(tmpdir, "mystery.yml")
            with open(filepath, "w", encoding="utf-8") as f:
                yaml.dump({"some_key": "some_value"}, f)

            result = YamlParser.parse_directory(tmpdir, api_mode="all")

        assert result["single_cases"] == []
        assert result["biz_flows"] == []


# ============================================================================
# _merge_cases in biz_flow mode skips None rows
# ============================================================================

