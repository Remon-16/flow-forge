"""Core orchestration logic for bidirectional Excel ↔ YAML conversion."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .excel_reader import read_excel
from .yaml_writer import write_biz_flows, write_interfaces, write_single_cases
from .excel_writer import write_excel as _write_excel

logger = logging.getLogger(__name__)


def _read_yaml_dir(dir_path: str | None) -> list[dict[str, object]]:
    """Read all YAML files from a directory, returning parsed dicts."""
    import yaml

    if not dir_path:
        return []
    p = Path(dir_path)
    if not p.is_dir():
        logger.warning("Directory not found, skipping: %s", dir_path)
        return []
    results: list[dict[str, object]] = []
    for f in sorted(p.glob("*.yaml")):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
            if isinstance(data, dict):
                # Remove case_type if present (it's metadata, not data)
                data.pop("case_type", None)
                results.append(data)
        except Exception:
            logger.warning("Failed to read YAML file: %s", f, exc_info=True)
    return results


def _read_yaml_biz_flows(dir_path: str | None) -> list[dict[str, object]]:
    """Read biz flow YAML files. Each file has ``sheet_name`` and ``steps``."""
    import yaml

    if not dir_path:
        return []
    p = Path(dir_path)
    if not p.is_dir():
        logger.warning("Directory not found, skipping: %s", dir_path)
        return []
    results: list[dict[str, object]] = []
    for f in sorted(p.glob("*.yaml")):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
            if isinstance(data, dict):
                data.pop("case_type", None)
                # Ensure steps exist
                if "steps" in data and isinstance(data["steps"], list):
                    results.append(data)
                else:
                    logger.warning("YAML file missing 'steps' list, skipping: %s", f)
        except Exception:
            logger.warning("Failed to read YAML file: %s", f, exc_info=True)
    return results


def excel_to_yaml(input_path: str, output_dir: str) -> dict[str, int]:
    """Convert an Excel workbook to YAML files.

    Returns:
        {"interfaces": N, "single_cases": N, "biz_flows": N}
    """
    logger.info("Converting Excel → YAML: %s → %s", input_path, output_dir)
    data = read_excel(input_path)

    n_iface = write_interfaces(data["interfaces"], output_dir)
    n_single = write_single_cases(data["single_cases"], output_dir)
    n_biz = write_biz_flows(data["biz_flows"], output_dir)

    return {"interfaces": n_iface, "single_cases": n_single, "biz_flows": n_biz}


def yaml_to_excel(
    output_path: str,
    *,
    interfaces_dir: str | None = None,
    single_cases_dir: str | None = None,
    biz_flows_dir: str | None = None,
) -> str:
    """Convert YAML directories to an Excel workbook.

    All three directories are optional. Sheets for missing directories
    are written with headers only (no data rows).

    Returns:
        The output Excel file path.
    """
    logger.info(
        "Converting YAML → Excel → %s (interfaces=%s, single=%s, biz=%s)",
        output_path, interfaces_dir, single_cases_dir, biz_flows_dir,
    )

    if not any([interfaces_dir, single_cases_dir, biz_flows_dir]):
        raise ValueError(
            "At least one of --interfaces, --single-cases, or --biz-flows must be provided."
        )

    interfaces = _read_yaml_dir(interfaces_dir) if interfaces_dir else []
    single_cases = _read_yaml_dir(single_cases_dir) if single_cases_dir else []
    biz_flows = _read_yaml_biz_flows(biz_flows_dir) if biz_flows_dir else []

    return _write_excel(interfaces, single_cases, biz_flows, output_path)
