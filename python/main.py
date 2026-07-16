#!/usr/bin/env python3
"""Flow Forge — API Test Executor

Usage:
    python main.py
    python main.py --envName prod --maxThread 10 --apiMode all
    python main.py --config /path/to/env.yml
"""

import argparse
import logging
import os
import sys
from typing import Any

# 注入 shared 包路径 — 使 flow_forge_schemas 可导入
# Inject shared package path — makes flow_forge_schemas importable
_SHARED = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "shared", "py"))
if os.path.isdir(_SHARED) and _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

from config.config_manager import initialize, get_all, ConfigError
from excel_reader.excel_parser import ExcelParser
from executor.factory import ExecutorFactory
from i18n import _, set_lang
from yaml_reader.yaml_parser import YamlParser
from reporter.html_writer import HTMLReportWriter

logger = logging.getLogger(__name__)


def _setup_logging(verbose: bool = False) -> None:
    """Configure logging with consistent format."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Flow Forge API Test Executor")
    parser.add_argument(
        "--config", type=str, default=None,
        help="Path to env.yml (default: env.yml next to this script)",
    )
    parser.add_argument("--scriptType", type=str, default=None, help="Script type")
    parser.add_argument("--envName", type=str, default=None, help="Environment name")
    parser.add_argument("--caseFilePath", type=str, default=None, help="Path to Excel test case file")
    parser.add_argument("--maxThread", type=int, default=None, help="Maximum number of threads")
    parser.add_argument("--reportName", type=str, default=None, help="Report name")
    parser.add_argument("--apiMode", type=str, default=None,
                        help="Test mode: single, biz, or all")
    parser.add_argument("--yamlDir", type=str, default=None,
                        help="Directory containing YAML test case files")
    parser.add_argument("--yamlFiles", type=str, default=None,
                        help="Comma-separated YAML file paths")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    return parser.parse_args(argv)


def _args_to_overrides(args: argparse.Namespace) -> dict:
    overrides = {}
    for key in ("scriptType", "envName", "caseFilePath", "maxThread", "reportName", "apiMode"):
        value = getattr(args, key, None)
        if value is not None:
            overrides[key] = value
    return overrides


def _load_config(args: argparse.Namespace) -> dict:
    """Load configuration from YAML file. Returns config dict or raises SystemExit."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    yml_path = args.config or os.path.join(script_dir, "env.yml")

    try:
        initialize(yml_path, _args_to_overrides(args))
    except FileNotFoundError as e:
        logger.error(str(e))
        sys.exit(2)
    except ConfigError as e:
        logger.error("Configuration error: %s", e)
        sys.exit(2)

    return get_all()


def _parse_test_cases(config: dict, args: argparse.Namespace):
    """Parse test cases from YAML directory, YAML files, or Excel file.

    Returns (single_cases, biz_flows).
    """
    api_mode = config.get("apiMode", "single")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    yaml_dir = args.yamlDir
    yaml_files = args.yamlFiles

    if yaml_dir:
        parsed = YamlParser.parse_directory(yaml_dir, api_mode)
    elif yaml_files:
        parsed = YamlParser.parse_files(yaml_files, api_mode)
    else:
        try:
            case_file = config["caseFilePath"]
            if not os.path.isabs(case_file):
                case_file = os.path.join(script_dir, case_file)
            parser = ExcelParser(case_file)
            parsed = parser.parse(api_mode)
        except (FileNotFoundError, ValueError) as e:
            logger.error(str(e))
            sys.exit(2)

    single_cases = parsed.get("single_cases", [])
    biz_flows = parsed.get("biz_flows", [])
    logger.info("Parsed: %d single cases, %d biz flows", len(single_cases), len(biz_flows))
    return single_cases, biz_flows


def _build_parse_error_results(errored: list) -> list:
    """Build error result dicts for biz flows that failed parsing."""
    results = []
    for bf in errored:
        results.append({
            "sheet_name": bf["sheet_name"],
            "api_name": bf["sheet_name"],
            "steps": [],
            "flow_chain": "",
            "failed_step": None,
            "passed": False,
            "parse_error": bf["parse_error"],
        })
    return results


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    _setup_logging(args.verbose)

    config = _load_config(args)

    # Initialize i18n from config
    set_lang(config.get("lang", "zh_CN"))

    api_mode = config.get("apiMode", "single")
    logger.info("Script type: %s, API mode: %s", config["scriptType"], api_mode)
    logger.info("Environment: %s", config["envName"])

    single_cases, biz_flows = _parse_test_cases(config, args)

    single_results = []
    biz_results = []

    if single_cases:
        try:
            executor = ExecutorFactory.create(config["scriptType"], config)
            single_results = executor.run(single_cases)
        except ValueError as e:
            logger.error(str(e))
            return 2

    if biz_flows:
        executable = [bf for bf in biz_flows if not bf.get("parse_error")]
        errored = [bf for bf in biz_flows if bf.get("parse_error")]

        biz_results.extend(_build_parse_error_results(errored))

        if executable:
            try:
                biz_executor = ExecutorFactory.create_biz(config)
                biz_run = biz_executor.run(executable)
                biz_results.extend(biz_run)
            except ValueError as e:
                logger.error(str(e))
                return 2

    try:
        writer = HTMLReportWriter(config)
        report_path = writer.write(single_results, biz_results)
    except (OSError, IOError) as e:
        logger.error("Failed to write report: %s", e)
        _print_summary(single_results, biz_results)
        return 1

    all_passed = _print_summary(single_results, biz_results)

    logger.info("Report: %s", report_path)

    # 输出 JSON 完成行供 Studio 解析 / Output JSON completion line for Studio parsing
    import json as _json
    _result = {
        "output": str(report_path),
        "single_cases": len(single_results),
        "biz_flows": len(biz_results),
        "single_passed": sum(1 for r in single_results if r.get("passed")),
        "biz_passed": sum(1 for r in biz_results if r.get("passed")),
        "all_passed": all_passed,
    }
    print(_json.dumps(_result, ensure_ascii=False))

    return 0 if all_passed else 1


def _print_summary(single_results: list, biz_results: list) -> bool:
    """Print test result summary. Returns True if all cases passed."""
    s_total = len(single_results)
    s_passed = sum(1 for r in single_results if r.get("passed"))
    b_total = len(biz_results)
    b_passed = sum(1 for r in biz_results if r.get("passed"))

    print(f"\n{'='*50}")
    print(_("cli.summary_single", total=s_total, passed=s_passed, failed=s_total - s_passed))
    print(_("cli.summary_biz", total=b_total, passed=b_passed, failed=b_total - b_passed))
    print(_("cli.summary_total", total=s_total + b_total, passed=s_passed + b_passed,
             failed=s_total + b_total - s_passed - b_passed))
    print(f"{'='*50}\n")

    return (s_passed + b_passed) == (s_total + b_total)


if __name__ == "__main__":
    sys.exit(main())
