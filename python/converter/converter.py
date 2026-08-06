"""Core orchestration logic for bidirectional Excel ↔ YAML conversion."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

import yaml

from .excel_reader import read_excel
from .yaml_writer import write_biz_flows, write_interfaces, write_single_cases
from .excel_writer import write_excel as _write_excel
from .common.utils import read_yaml_dir
from i18n import _

logger = logging.getLogger(__name__)


def excel_to_yaml(input_path: str, output_dir: str) -> dict[str, int]:
    """Convert an Excel workbook to YAML files.

    Returns:
        {"interfaces": N, "single_cases": N, "biz_flows": N}
    """
    logger.info(
        _("converter.converting_excel_yaml", input=input_path, output=output_dir)
    )
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
        _(
            "converter.converting_yaml_excel",
            output=output_path,
            interfaces=interfaces_dir,
            single=single_cases_dir,
            biz=biz_flows_dir,
        )
    )

    if not any([interfaces_dir, single_cases_dir, biz_flows_dir]):
        raise ValueError(
            "At least one of --interfaces, --single-cases, or --biz-flows must be provided."
        )

    interfaces = read_yaml_dir(interfaces_dir) if interfaces_dir else []
    single_cases = read_yaml_dir(single_cases_dir) if single_cases_dir else []
    biz_flows = (
        read_yaml_dir(
            biz_flows_dir,
            validator=lambda d: "steps" in d and isinstance(d["steps"], list),
        )
        if biz_flows_dir
        else []
    )

    return _write_excel(interfaces, single_cases, biz_flows, output_path)
