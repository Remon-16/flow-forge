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

from config.config_manager import initialize, get_all, ConfigError
from excel_reader.excel_parser import ExcelParser
from executor.factory import ExecutorFactory
from yaml_reader.yaml_parser import YamlParser
from reporter.html_writer import HTMLReportWriter

logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
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
    return parser.parse_args()


def _args_to_overrides(args: argparse.Namespace) -> dict:
    overrides = {}
    for key in ("scriptType", "envName", "caseFilePath", "maxThread", "reportName", "apiMode"):
        value = getattr(args, key, None)
        if value is not None:
            overrides[key] = value
    return overrides


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    args = _parse_args()
    script_dir = os.path.dirname(os.path.abspath(__file__))
    yml_path = args.config or os.path.join(script_dir, "env.yml")

    try:
        initialize(yml_path, _args_to_overrides(args))
    except FileNotFoundError as e:
        logger.error(str(e))
        return 2
    except ConfigError as e:
        logger.error("Configuration error: %s", e)
        return 2

    config = get_all()
    api_mode = config.get("apiMode", "single")
    logger.info("Script type: %s, API mode: %s", config["scriptType"], api_mode)
    logger.info("Environment: %s", config["envName"])

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
            return 2

    single_cases = parsed.get("single_cases", [])
    biz_flows = parsed.get("biz_flows", [])
    logger.info("Parsed: %d single cases, %d biz flows", len(single_cases), len(biz_flows))

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

        for bf in errored:
            biz_results.append({
                "sheet_name": bf["sheet_name"],
                "api_name": bf["sheet_name"],
                "steps": [],
                "flow_chain": "",
                "failed_step": None,
                "passed": False,
                "parse_error": bf["parse_error"],
            })

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

    _print_summary(single_results, biz_results)

    total_s = len(single_results)
    total_b = len(biz_results)
    total = total_s + total_b
    s_passed = sum(1 for r in single_results if r.get("passed"))
    b_passed = sum(1 for r in biz_results if r.get("passed"))
    all_passed = s_passed + b_passed

    logger.info("Report: %s", report_path)

    if all_passed == total:
        return 0
    return 1


def _print_summary(single_results: list, biz_results: list) -> None:
    s_total = len(single_results)
    s_passed = sum(1 for r in single_results if r.get("passed"))
    b_total = len(biz_results)
    b_passed = sum(1 for r in biz_results if r.get("passed"))

    print(f"\n{'='*50}")
    print(f"  Single: {s_total} total | {s_passed} passed | {s_total - s_passed} failed")
    print(f"  Biz   : {b_total} total | {b_passed} passed | {b_total - b_passed} failed")
    print(f"  Total : {s_total + b_total} total | {s_passed + b_passed} passed | "
          f"{s_total + b_total - s_passed - b_passed} failed")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    sys.exit(main())
