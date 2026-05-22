import json
import logging
import os
from typing import Any, Dict, List, Optional

import openpyxl

from core.deep_merge import deep_merge

logger = logging.getLogger(__name__)

_API_SHEET_NAME = 0
_CASE_SHEET_NAME = 1

_SIMPLE_FIELDS = ("APIName", "Method", "URL", "StatusCode")
_JSON_FIELDS = ("RequestHead", "RequestBody")
_SHEET1_REQUIRED = ("TestID", "APIName", "Method", "URL", "StatusCode")
_SHEET2_REQUIRED = ("TestID", "RelevanceID")


class ExcelParser:
    """Reads a two-sheet Excel test-case file and returns a merged list of test cases."""

    def __init__(self, file_path: str):
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"Excel file not found: {file_path}")
        self.file_path = file_path

    def parse(self) -> List[Dict[str, Any]]:
        wb = openpyxl.load_workbook(self.file_path, data_only=True)
        try:
            if len(wb.sheetnames) < 2:
                raise ValueError(
                    f"Expected at least 2 sheets, got {len(wb.sheetnames)}: {wb.sheetnames}"
                )

            api_defs = self._read_api_definitions(wb.worksheets[_API_SHEET_NAME])
            logger.info("Read %d API definitions from sheet 1", len(api_defs))

            test_cases = self._read_test_cases(wb.worksheets[_CASE_SHEET_NAME])
            logger.info("Read %d test cases from sheet 2", len(test_cases))

            merged = self._merge_cases(api_defs, test_cases)
            logger.info("Merged into %d test cases", len(merged))
            return merged
        finally:
            wb.close()

    def _read_api_definitions(self, ws) -> List[Dict[str, Any]]:
        return self._read_sheet(ws, list(_SHEET1_REQUIRED))

    def _read_test_cases(self, ws) -> List[Dict[str, Any]]:
        return self._read_sheet(ws, list(_SHEET2_REQUIRED))

    def _read_sheet(self, ws, required_columns: List[str]) -> List[Dict[str, Any]]:
        headers = []
        for col_idx, cell in enumerate(ws[1], start=1):
            if cell.value is not None:
                headers.append((col_idx, str(cell.value).strip()))

        header_names = [h[1] for h in headers]
        missing = [c for c in required_columns if c not in header_names]
        if missing:
            raise ValueError(
                f"Sheet '{ws.title}' is missing required columns: {missing}"
            )

        col_map = {h[1]: h[0] for h in headers}
        rows = []
        for row_idx in range(2, ws.max_row + 1):
            row_data = {}
            for name, col in col_map.items():
                row_data[name] = ws.cell(row=row_idx, column=col).value
            if all(v is None for v in row_data.values()):
                continue
            rows.append(row_data)

        return rows

    def _merge_cases(
        self, api_defs: List[Dict[str, Any]], test_cases: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        api_lookup: Dict[str, Dict[str, Any]] = {}
        for row in api_defs:
            tid = row.get("TestID")
            if tid:
                api_lookup[str(tid)] = row

        merged = []
        for tc in test_cases:
            relevance_id = str(tc.get("RelevanceID", ""))
            api_def = api_lookup.get(relevance_id)

            if api_def is None:
                logger.warning(
                    "RelevanceID '%s' not found in API definitions, using test case as-is",
                    relevance_id,
                )
                merged.append(self._build_result(tc, None))
                continue

            merged.append(self._build_result(tc, api_def))

        return merged

    def _build_result(
        self, tc: Dict[str, Any], api_def: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        result = {}

        for field in _SIMPLE_FIELDS:
            tc_val = tc.get(field)
            api_val = api_def.get(field) if api_def else None
            result[self._normalize_key(field)] = (
                tc_val if tc_val not in (None, "") else api_val
            )

        for field in _JSON_FIELDS:
            tc_json = self._safe_parse_json(tc.get(field), field, tc.get("TestID"))
            api_json = (
                self._safe_parse_json(api_def.get(field), field, api_def.get("TestID"))
                if api_def
                else {}
            )
            result[self._normalize_key(field)] = deep_merge(api_json, tc_json)

        assert_field = tc.get("AssertDict")
        if assert_field not in (None, ""):
            result["assert_dict"] = self._safe_parse_json(
                assert_field, "AssertDict", tc.get("TestID")
            )
        elif api_def:
            api_assert = api_def.get("AssertDict")
            result["assert_dict"] = (
                self._safe_parse_json(api_assert, "AssertDict", api_def.get("TestID"))
                if api_assert not in (None, "")
                else {}
            )
        else:
            result["assert_dict"] = {}

        result["test_id"] = str(tc.get("TestID", ""))
        result["tag"] = str(tc.get("Tag", "")) if tc.get("Tag") is not None else ""
        result["remark"] = str(tc.get("Remark", "")) if tc.get("Remark") is not None else ""

        return result

    @staticmethod
    def _normalize_key(field: str) -> str:
        mapping = {
            "APIName": "api_name",
            "Method": "method",
            "URL": "url",
            "StatusCode": "status_code",
            "RequestHead": "request_head",
            "RequestBody": "request_body",
        }
        return mapping.get(field, field.lower())

    @staticmethod
    def _safe_parse_json(
        raw: Any, field_name: str, test_id: Optional[str]
    ) -> Dict[str, Any]:
        if raw is None:
            return {}
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            stripped = raw.strip()
            if not stripped:
                return {}
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                logger.warning(
                    "Failed to parse %s as JSON for test case '%s', using empty dict",
                    field_name,
                    test_id,
                )
                return {}
        return {}
