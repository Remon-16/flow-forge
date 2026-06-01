"""Markdown API table parser.

Parses Markdown tables with API interface definitions into InterfaceDef list.
Expected table columns: TestID, APIName, AppName, Method, URL, StatusCode,
                        RequestHead, RequestBody, AssertDict, Remark
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from models.schema import InterfaceDef

logger = logging.getLogger(__name__)

_COL_ALIASES: Dict[str, List[str]] = {
    "test_id": ["testid", "test_id", "id", "api_id"],
    "api_name": ["apiname", "api_name", "name", "interface_name"],
    "app_name": ["appname", "app_name", "app", "application"],
    "method": ["method", "http_method"],
    "url": ["url", "path", "endpoint", "api_path"],
    "request_head": ["requesthead", "request_head", "header", "headers", "req_head"],
    "request_body": ["requestbody", "request_body", "body", "req_body", "params"],
    "status_code": ["statuscode", "status_code", "status", "expected_status"],
    "assert_dict": ["assertdict", "assert_dict", "assertion", "assert", "check"],
    "remark": ["remark", "note", "description", "desc", "comment"],
}


def _normalize_col(name: str) -> Optional[str]:
    key = name.strip().lower().replace(" ", "_").replace("-", "_")
    for col_name, aliases in _COL_ALIASES.items():
        if key in aliases:
            return col_name
    return None


def _strip_cell(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _find_tables(lines: List[str]) -> List[tuple]:
    """Find markdown tables and return (header_line_index, data_line_indices)."""
    tables = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("|") and "---" not in line:
            # Potential header
            if i + 1 < len(lines) and "---" in lines[i + 1]:
                header_idx = i
                data_indices = []
                j = i + 2
                while j < len(lines) and lines[j].strip().startswith("|"):
                    data_indices.append(j)
                    j += 1
                tables.append((header_idx, data_indices))
                i = j
                continue
        i += 1
    return tables


def _parse_row(line: str) -> List[str]:
    """Parse a markdown table row into cell values."""
    # Remove leading/trailing pipes, then split by |
    clean = line.strip().strip("|")
    # Split but be careful with escaped pipes
    cells = [c.strip() for c in clean.split("|")]
    return cells


class MarkdownParser:
    """Parse API interface definitions from Markdown tables."""

    @staticmethod
    def parse(file_path: str) -> List[InterfaceDef]:
        """Parse a Markdown file and extract InterfaceDefs from API tables."""
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        lines = content.split("\n")
        tables = _find_tables(lines)

        all_interfaces: List[InterfaceDef] = []
        for header_idx, data_indices in tables:
            header_cells = _parse_row(lines[header_idx])
            column_map: Dict[str, int] = {}
            for idx, cell in enumerate(header_cells):
                col_name = _normalize_col(cell)
                if col_name:
                    column_map[col_name] = idx

            # Must have at minimum: url and method
            if "method" not in column_map and "url" not in column_map:
                continue

            for row_idx in data_indices:
                cells = _parse_row(lines[row_idx])

                def get_val(col: str) -> str:
                    if col not in column_map:
                        return ""
                    ci = column_map[col]
                    return _strip_cell(cells[ci]) if ci < len(cells) else ""

                test_id = get_val("test_id")
                method = get_val("method").upper() or "GET"
                url = get_val("url")

                if not test_id or not url:
                    # Auto-generate test_id if missing
                    clean = url.strip("/").replace("/", "_").replace("-",
                                                                     "_").lower()
                    test_id = f"api_{clean}_{method.lower()}" if clean else ""

                if not test_id:
                    continue

                # Parse JSON fields
                head_str = get_val("request_head")
                body_str = get_val("request_body")
                assert_str = get_val("assert_dict")

                request_head = MarkdownParser._safe_json_parse(head_str)
                request_body = MarkdownParser._safe_json_parse(body_str)
                assert_dict = MarkdownParser._safe_json_parse(assert_str)

                status_str = get_val("status_code")
                try:
                    status_code = int(status_str) if status_str else 200
                except ValueError:
                    status_code = 200

                all_interfaces.append(InterfaceDef(
                    test_id=test_id,
                    api_name=get_val("api_name"),
                    app_name=get_val("app_name"),
                    method=method,
                    url=url,
                    request_head=request_head,
                    request_body=request_body,
                    status_code=status_code,
                    assert_dict=assert_dict,
                    remark=get_val("remark"),
                ))

        return all_interfaces

    @staticmethod
    def _safe_json_parse(raw: str) -> Dict[str, Any]:
        """Parse a JSON string safely, returning {} on failure."""
        if not raw:
            return {}
        # Handle single-quote JSON
        normalized = raw.strip()
        if normalized.startswith("'") and normalized.endswith("'"):
            normalized = normalized[1:-1]
        try:
            return json.loads(normalized)
        except (json.JSONDecodeError, ValueError):
            try:
                # Try replacing single quotes with double quotes
                return json.loads(normalized.replace("'", '"'))
            except (json.JSONDecodeError, ValueError):
                logger.warning("Failed to parse JSON: %s...", raw[:80])
                return {}
