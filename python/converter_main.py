#!/usr/bin/env python3
"""Test case format converter — Excel ↔ YAML bidirectional conversion.

Usage:
    # Excel → YAML
    python converter_main.py excel2yaml --input cases.xlsx --output ./output/

    # YAML → Excel (all three directories optional)
    python converter_main.py yaml2excel \\
        --interfaces ./cases/interfaces/ \\
        --single-cases ./cases/single_cases/ \\
        --biz-flows ./cases/biz_flows/ \\
        --output cases.xlsx
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

# 注入 shared 包路径 — 使 flow_forge_schemas 可导入
# Inject shared package path — makes flow_forge_schemas importable
_SHARED = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "shared", "py"))
if os.path.isdir(_SHARED) and _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

from converter.converter import excel_to_yaml, yaml_to_excel
from converter.pytest_writer import yaml_to_pytest, excel_to_pytest
from i18n import _

logger = logging.getLogger("converter")


# 委托给 shared/py/flow_forge_logging 模块，确保与 agent/executor 格式统一
# Delegate to shared/py/flow_forge_logging for consistent format across all subprocesses
from flow_forge_logging import setup_studio_logging as _setup_logging


def _cmd_excel2yaml(args: argparse.Namespace) -> int:
    counts = excel_to_yaml(args.input, args.output)
    total = sum(counts.values())
    if total == 0:
        logger.warning("No test cases found in the input Excel file.")
        return 1
    print(_("cli.converted_count",
             interfaces=counts['interfaces'],
             single=counts['single_cases'],
             biz=counts['biz_flows'],
             output=args.output))
    # JSON 完成行供 Studio 解析 / JSON completion line for Studio parsing
    import json as _json
    print(_json.dumps({"output": str(args.output), "command": "excel2yaml"}, ensure_ascii=False))
    return 0


def _cmd_yaml2excel(args: argparse.Namespace) -> int:
    out = yaml_to_excel(
        args.output,
        interfaces_dir=args.interfaces,
        single_cases_dir=args.single_cases,
        biz_flows_dir=args.biz_flows,
    )
    print(_("cli.excel_written", path=out))
    import json as _json
    print(_json.dumps({"output": str(out), "command": "yaml2excel"}, ensure_ascii=False))
    return 0


def _cmd_yaml2pytest(args: argparse.Namespace) -> int:
    counts = yaml_to_pytest(
        args.output,
        interfaces_dir=args.interfaces,
        single_cases_dir=args.single_cases,
        biz_flows_dir=args.biz_flows,
        config_dir=args.config_dir,
        processors_dir=args.processors_dir,
    )
    logger.info(
        _("cli.pytest_generated",
           single=counts['single_cases'],
           biz=counts['biz_flows'],
           custom=counts['bundled_processors'],
           output=args.output))
    import json as _json
    print(_json.dumps({"output": str(args.output), "command": "yaml2pytest"}, ensure_ascii=False))
    return 0


def _cmd_excel2pytest(args: argparse.Namespace) -> int:
    counts = excel_to_pytest(
        args.input,
        args.output,
        config_dir=args.config_dir,
        processors_dir=args.processors_dir,
    )
    logger.info(
        _("cli.pytest_generated",
           single=counts['single_cases'],
           biz=counts['biz_flows'],
           custom=counts['bundled_processors'],
           output=args.output))
    import json as _json
    print(_json.dumps({"output": str(args.output), "command": "excel2pytest"}, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    """主入口 — 子命令和参数定义来自 shared/schemas/cli/converter.json。
    Main entry — subcommands and arg definitions from shared schema."""
    # 从 shared schema 自动生成 parser（含子命令）/ Auto-generate parser (with subcommands) from shared schema
    from flow_forge_schemas.cli import load_cli_schema, add_subcommand_args
    schema = load_cli_schema("converter")
    parser = argparse.ArgumentParser(
        prog="converter",
        description="Convert Flow Forge test cases between Excel and YAML formats.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    add_subcommand_args(sub, schema)

    args = parser.parse_args(argv)
    _setup_logging(args.verbose)

    try:
        if args.command == "excel2yaml":
            return _cmd_excel2yaml(args)
        elif args.command == "yaml2excel":
            return _cmd_yaml2excel(args)
        elif args.command == "yaml2pytest":
            return _cmd_yaml2pytest(args)
        elif args.command == "excel2pytest":
            return _cmd_excel2pytest(args)
    except (FileNotFoundError, ValueError) as e:
        logger.error("%s", e)
        return 2
    except Exception:
        logger.exception("Unexpected error")
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
