#!/usr/bin/env python3
"""Flow Forge — API Test Executor

Usage:
    python main.py
    python main.py --envName prod --maxThread 10
    python main.py --config /path/to/env.yml
"""

import argparse
import logging
import os
import sys

from config.config_manager import initialize, get_all, ConfigError
from executor.factory import ExecutorFactory
from excel_reader.excel_parser import ExcelParser
from reporter.md_writer import MarkdownReportWriter

logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Flow Forge API Test Executor",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to env.yml configuration file (default: env.yml next to this script)",
    )
    parser.add_argument("--scriptType", type=str, default=None, help="Script type")
    parser.add_argument("--baseURL", type=str, default=None, help="Base URL for API requests")
    parser.add_argument("--envName", type=str, default=None, help="Environment name")
    parser.add_argument("--caseFilePath", type=str, default=None, help="Path to Excel test case file")
    parser.add_argument("--maxThread", type=int, default=None, help="Maximum number of threads")
    parser.add_argument("--reportName", type=str, default=None, help="Report name")
    return parser.parse_args()


def _args_to_overrides(args: argparse.Namespace) -> dict:
    overrides = {}
    for key in ("scriptType", "baseURL", "envName", "caseFilePath", "maxThread", "reportName"):
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
    logger.info("Script type: %s", config["scriptType"])
    logger.info("Environment: %s", config["envName"])
    logger.info("Base URL: %s", config["baseURL"])

    try:
        parser = ExcelParser(config["caseFilePath"])
        cases = parser.parse()
    except (FileNotFoundError, ValueError) as e:
        logger.error(str(e))
        return 2

    if not cases:
        logger.warning("No test cases found — nothing to execute")
        return 0

    try:
        executor = ExecutorFactory.create(config["scriptType"], config)
    except ValueError as e:
        logger.error(str(e))
        return 2

    results = executor.run(cases)

    try:
        writer = MarkdownReportWriter(config)
        report_path = writer.write(results)
    except (OSError, IOError) as e:
        logger.error("Failed to write report: %s", e)
        _print_summary(results)
        return 1

    _print_summary(results)

    total = len(results)
    passed = sum(1 for r in results if r.get("passed"))
    logger.info("Report: %s", report_path)

    if passed == total:
        return 0
    return 1


def _print_summary(results: list) -> None:
    total = len(results)
    passed = sum(1 for r in results if r.get("passed"))
    failed = total - passed
    print(f"\n{'='*50}")
    print(f"  Total: {total}  |  Passed: {passed}  |  Failed: {failed}")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    sys.exit(main())
