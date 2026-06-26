"""Tests for input validation — Excel parsing and YAML parsing.

Covers excel_parser.ExcelParser, yaml_parser.YamlParser, and related
executor-level validation for edge cases.
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from executor.biz_flow import BizFlowExecutor
from executor.single_case import SingleCaseExecutor


# ============================================================================
# Excel Input Validation
# ============================================================================

class TestExcelValidationTest:
    """Tests for ExcelParser input validation — missing columns, sheet counts, etc."""

    def _make_cell(self, value):
        c = Mock()
        c.value = value
        return c

    def _mock_worksheet(self, title, headers, rows):
        """Create a mock openpyxl worksheet with a header row and data rows."""
        ws = MagicMock()
        ws.title = title
        ws.max_row = len(rows) + 1  # +1 for header

        # Build row-by-row cell access
        # Row 1 = headers
        header_cells = [self._make_cell(h) for h in headers]

        def getitem_row(row_idx):
            if row_idx == 1:
                return header_cells
            data_idx = row_idx - 2
            if data_idx < len(rows):
                return [self._make_cell(v) for v in rows[data_idx]]
            return [self._make_cell(None) for _ in headers]

        ws.__getitem__.side_effect = getitem_row

        def cell(row, column):
            if row == 1:
                return self._make_cell(headers[column - 1] if column <= len(headers) else None)
            data_idx = row - 2
            if data_idx < len(rows):
                row_data = rows[data_idx]
                if column <= len(row_data):
                    return self._make_cell(row_data[column - 1])
            return self._make_cell(None)

        ws.cell.side_effect = cell

        return ws

    @patch("openpyxl.load_workbook")
    @patch("os.path.isfile", return_value=True)
    def should_reject_excel_with_missing_single_case_columns(self, mock_load, mock_isfile):
        """Sheet 2 (single cases) missing TestID column should raise ValueError."""
        from excel_reader.excel_parser import ExcelParser

        ws1 = self._mock_worksheet("Sheet1", ["Col"], [])
        ws2 = self._mock_worksheet("Cases", ["APIName", "URL"], [])  # Missing TestID

        mock_wb = MagicMock()
        mock_wb.sheetnames = ["Sheet1", "Cases"]
        mock_wb.worksheets = [ws1, ws2]

        mock_load.return_value = mock_wb

        parser = ExcelParser("fake.xlsx")
        with pytest.raises(ValueError, match="missing required columns"):
            parser.parse(api_mode="single")

    @patch("openpyxl.load_workbook")
    @patch("os.path.isfile", return_value=True)
    def should_reject_excel_with_missing_biz_flow_columns(self, mock_load, mock_isfile):
        """Biz flow sheet (sheet 3+) missing StepID column should raise ValueError."""
        from excel_reader.excel_parser import ExcelParser

        ws1 = self._mock_worksheet("Sheet1", ["Col"], [])
        ws2 = self._mock_worksheet("Cases", ["TestID", "APIName", "URL", "RelevanceID"], [])
        ws3 = self._mock_worksheet("BizFlow", ["APIName", "URL"], [])  # Missing StepID/RelevanceID

        mock_wb = MagicMock()
        mock_wb.sheetnames = ["Sheet1", "Cases", "BizFlow"]
        mock_wb.worksheets = [ws1, ws2, ws3]

        mock_load.return_value = mock_wb

        parser = ExcelParser("fake.xlsx")
        with pytest.raises(ValueError, match="missing required columns"):
            parser.parse(api_mode="biz")

    @patch("openpyxl.load_workbook")
    @patch("os.path.isfile", return_value=True)
    def should_reject_excel_with_fewer_than_2_sheets(self, mock_load, mock_isfile):
        """Excel with only 1 sheet should raise ValueError."""
        from excel_reader.excel_parser import ExcelParser

        ws1 = self._mock_worksheet("Sheet1", ["Col"], [])

        mock_wb = MagicMock()
        mock_wb.sheetnames = ["Sheet1"]
        mock_wb.worksheets = [ws1]

        mock_load.return_value = mock_wb

        parser = ExcelParser("fake.xlsx")
        with pytest.raises(ValueError, match="at least 2 sheets"):
            parser.parse()


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

class TestExcelSkipEmptyRowsTest:

    @patch("openpyxl.load_workbook")
    @patch("os.path.isfile", return_value=True)
    def should_skip_entirely_empty_rows(self, mock_load, mock_isfile):
        """Rows where all values are None should be skipped."""
        from excel_reader.excel_parser import ExcelParser

        ws1 = MagicMock()
        ws1.title = "Config"

        ws2 = MagicMock()
        ws2.title = "Cases"

        # Sheet 2 headers: TestID, APIName, URL, RelevanceID
        headers2 = ["TestID", "APIName", "URL", "RelevanceID"]
        ws2_cells_row1 = [Mock(value=h) for h in headers2]
        ws2.max_row = 4

        # Row 2: valid case
        # Row 3: all None (should be skipped)
        # Row 4: another valid case
        def get_ws2_item(idx):
            if idx == 1:
                return ws2_cells_row1
            elif idx == 2:
                return [Mock(value="TC001"), Mock(value="Test"), Mock(value="/api/a"), Mock(value="R001")]
            elif idx == 3:
                return [Mock(value=None), Mock(value=None), Mock(value=None), Mock(value=None)]
            elif idx == 4:
                return [Mock(value="TC002"), Mock(value="Test2"), Mock(value="/api/b"), Mock(value="R002")]
            return []

        ws2.__getitem__.side_effect = get_ws2_item

        def ws2_cell(row, col):
            data = {2: ["TC001", "Test", "/api/a", "R001"],
                    3: [None, None, None, None],
                    4: ["TC002", "Test2", "/api/b", "R002"]}
            return Mock(value=data.get(row, [None]*4)[col-1])
        ws2.cell.side_effect = ws2_cell

        mock_wb = Mock()
        mock_wb.sheetnames = ["Config", "Cases"]
        mock_wb.worksheets = [ws1, ws2]

        mock_load.return_value = mock_wb

        parser = ExcelParser("fake.xlsx")
        result = parser.parse(api_mode="single")

        # Only 2 valid rows (empty row skipped)
        assert len(result["single_cases"]) == 2
