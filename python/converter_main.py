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


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = []
    root.addHandler(handler)


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
    return 0


def _cmd_yaml2excel(args: argparse.Namespace) -> int:
    out = yaml_to_excel(
        args.output,
        interfaces_dir=args.interfaces,
        single_cases_dir=args.single_cases,
        biz_flows_dir=args.biz_flows,
    )
    print(_("cli.excel_written", path=out))
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
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="converter",
        description="Convert Flow Forge test cases between Excel and YAML formats.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # excel2yaml
    p_e2y = sub.add_parser("excel2yaml", help="Convert Excel (.xlsx) → YAML directory")
    p_e2y.add_argument("--input", "-i", required=True, help="Input .xlsx file path")
    p_e2y.add_argument("--output", "-o", required=True, help="Output directory for YAML files")
    p_e2y.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")

    # yaml2excel
    p_y2e = sub.add_parser("yaml2excel", help="Convert YAML directories → Excel (.xlsx)")
    p_y2e.add_argument("--interfaces", help="Directory containing interface YAML files")
    p_y2e.add_argument("--single-cases", help="Directory containing single case YAML files")
    p_y2e.add_argument("--biz-flows", help="Directory containing biz flow YAML files")
    p_y2e.add_argument("--output", "-o", required=True, help="Output .xlsx file path")
    p_y2e.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")

    # yaml2pytest
    p_y2p = sub.add_parser("yaml2pytest", help="Convert YAML directories → pytest test files")
    p_y2p.add_argument("--interfaces", help="Directory containing interface YAML files")
    p_y2p.add_argument("--single-cases", help="Directory containing single case YAML files")
    p_y2p.add_argument("--biz-flows", help="Directory containing biz flow YAML files")
    p_y2p.add_argument("--output", "-o", required=True, help="Output directory for pytest files")
    p_y2p.add_argument("--config-dir", help="Directory containing env-*.yml files (default: python/)")
    p_y2p.add_argument("--processors-dir", help="Directory containing custom processors")
    p_y2p.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")

    # excel2pytest
    p_e2p = sub.add_parser("excel2pytest", help="Convert Excel (.xlsx) → pytest test files")
    p_e2p.add_argument("--input", "-i", required=True, help="Input .xlsx file path")
    p_e2p.add_argument("--output", "-o", required=True, help="Output directory for pytest files")
    p_e2p.add_argument("--config-dir", help="Directory containing env-*.yml files (default: python/)")
    p_e2p.add_argument("--processors-dir", help="Directory containing custom processors")
    p_e2p.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")

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
