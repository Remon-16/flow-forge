"""pytest 代码生成入口 — 编排 YAML/Excel 读取 → 代码生成 → 文件写入。
   pytest code generation entry — orchestrate YAML/Excel reading → code generation → file writing."""

from __future__ import annotations

import logging
import os
from typing import Any

from .common.utils import read_yaml_dir
from .common.export_utils import write_ff_compat, write_env_configs, bundle_processors
from .pytest.writers import write_conftest, write_single_tests, write_biz_flow_tests

logger = logging.getLogger(__name__)


def _write_setup_files(output_dir: str, config_dir: str, processors_dir: str | None) -> int:
    """写入所有导出格式都需要的基础支撑文件。
       Write base support files common to all export formats."""
    os.makedirs(output_dir, exist_ok=True)
    config_src = config_dir or "."
    write_conftest(output_dir)
    write_ff_compat(output_dir)
    write_env_configs(output_dir, config_src)
    return bundle_processors(output_dir, custom_processors_dir=processors_dir)


def yaml_to_pytest(
    output_dir: str,
    *,
    interfaces_dir: str | None = None,
    single_cases_dir: str | None = None,
    biz_flows_dir: str | None = None,
    config_dir: str | None = None,
    processors_dir: str | None = None,
) -> dict[str, int]:
    """YAML 用例目录 → 独立 pytest 测试文件。
       Convert YAML case directories to standalone pytest files.

       三个目录均可选，至少提供一个。
       All three directories are optional. At least one must be provided.
    """
    if not any([interfaces_dir, single_cases_dir, biz_flows_dir]):
        raise ValueError(
            "At least one of --interfaces, --single-cases, or --biz-flows must be provided."
        )

    n_custom = _write_setup_files(output_dir, config_dir or ".", processors_dir)

    single_cases = read_yaml_dir(single_cases_dir) if single_cases_dir else []
    biz_flows = (
        read_yaml_dir(
            biz_flows_dir,
            validator=lambda d: "steps" in d and isinstance(d["steps"], list),
        )
        if biz_flows_dir
        else []
    )

    n_single = write_single_tests(single_cases, output_dir)
    n_biz = write_biz_flow_tests(biz_flows, output_dir)

    return {"single_cases": n_single, "biz_flows": n_biz, "bundled_processors": n_custom}


def excel_to_pytest(
    input_path: str,
    output_dir: str,
    *,
    config_dir: str | None = None,
    processors_dir: str | None = None,
) -> dict[str, int]:
    """Excel 用例文件 → 独立 pytest 测试文件。
       Convert Excel workbook to standalone pytest files.

       自动检测 sheet：API Definitions → 跳过，Single Cases → 单接口，其余 → 业务链路。
       Auto-detects sheets: API Definitions → skipped, Single Cases → single, others → biz flow.
    """
    from .excel_reader import read_excel

    logger.info("Converting Excel → pytest: %s → %s", input_path, output_dir)
    data = read_excel(input_path)

    n_custom = _write_setup_files(output_dir, config_dir or ".", processors_dir)

    n_single = write_single_tests(data.get("single_cases", []), output_dir)
    n_biz = write_biz_flow_tests(data.get("biz_flows", []), output_dir)

    return {"single_cases": n_single, "biz_flows": n_biz, "bundled_processors": n_custom}
