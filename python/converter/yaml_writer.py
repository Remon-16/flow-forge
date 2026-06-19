"""Write structured test case data to YAML files.

Follows the same directory layout as the Agent's YamlWriter:
  output_dir/
    interfaces/{test_id}.yaml
    single_cases/{test_id}.yaml
    biz_flows/{sheet_name}.yaml
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


def _safe_filename(name: str) -> str:
    """Replace path-unsafe characters in a filename stem."""
    for ch in "/\\:*?\"<>|":
        name = name.replace(ch, "_")
    return name


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_interfaces(
    interfaces: list[dict[str, object]], output_dir: str
) -> int:
    """Write interface definitions to output_dir/interfaces/*.yaml."""
    if not interfaces:
        return 0
    dir_path = Path(output_dir) / "interfaces"
    _ensure_dir(dir_path)
    count = 0
    for iface in interfaces:
        d = dict(iface)
        d["case_type"] = "interfaces"
        test_id = str(d.get("test_id", "unknown"))
        stem = _safe_filename(test_id)
        file_path = dir_path / f"{stem}.yaml"
        with open(file_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(d, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
        count += 1
    logger.info("Wrote %d interface YAML files to %s", count, dir_path)
    return count


def write_single_cases(
    cases: list[dict[str, object]], output_dir: str
) -> int:
    """Write single API test cases to output_dir/single_cases/*.yaml.

    On filename collision appends _v2, _v3, etc.
    """
    if not cases:
        return 0
    dir_path = Path(output_dir) / "single_cases"
    _ensure_dir(dir_path)
    count = 0
    for case in cases:
        d = dict(case)
        d["case_type"] = "single"
        test_id = str(d.get("test_id", "unknown"))
        stem = _safe_filename(test_id)
        file_path = dir_path / f"{stem}.yaml"

        if file_path.exists():
            i = 2
            while file_path.exists():
                file_path = dir_path / f"{stem}_v{i}.yaml"
                i += 1
            d["test_id"] = f"{test_id}_v{i - 1}"

        with open(file_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(d, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
        count += 1
    logger.info("Wrote %d single case YAML files to %s", count, dir_path)
    return count


def write_biz_flows(
    flows: list[dict[str, object]], output_dir: str
) -> int:
    """Write business flow test cases to output_dir/biz_flows/*.yaml.

    On filename collision appends _v2, _v3, etc.
    """
    if not flows:
        return 0
    dir_path = Path(output_dir) / "biz_flows"
    _ensure_dir(dir_path)
    count = 0
    for flow in flows:
        d = dict(flow)
        d["case_type"] = "biz"
        sheet_name = str(d.get("sheet_name", "unknown"))
        stem = _safe_filename(sheet_name)
        file_path = dir_path / f"{stem}.yaml"

        if file_path.exists():
            i = 2
            while file_path.exists():
                file_path = dir_path / f"{stem}_v{i}.yaml"
                i += 1
            d["sheet_name"] = f"{sheet_name}_v{i - 1}"

        with open(file_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(d, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
        count += 1
    logger.info("Wrote %d biz flow YAML files to %s", count, dir_path)
    return count
