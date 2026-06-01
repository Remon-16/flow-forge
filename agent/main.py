#!/usr/bin/env python3
"""Flow Forge — API Test Case Generation Agent CLI.

Usage:
    # Generate test plan only (for human review)
    python main.py --requirement docs/req.md --api docs/api.yaml --plan-only

    # Generate Excel from a confirmed plan
    python main.py --from-plan plan_20260601_120000.md --api docs/api.yaml --output testcase.xlsx

    # One-shot full pipeline (skip confirmation)
    python main.py --requirement docs/req.md --api docs/api.yaml --output testcase.xlsx
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from agents.excel_writer import ExcelWriter
from config.settings import load_settings
from pipeline.orchestrator import PipelineOrchestrator

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(level=level, format=fmt, datefmt="%H:%M:%S")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Flow Forge — API Test Case Generation Agent"
    )
    p.add_argument(
        "--requirement",
        nargs="+",
        help="Requirement document path(s) (.txt, .md, .pdf)",
    )
    p.add_argument(
        "--api",
        help="API documentation path (OpenAPI .yaml/.json or Markdown .md)",
    )
    p.add_argument(
        "--output",
        default=f"testcase_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
        help="Output Excel file path",
    )
    p.add_argument(
        "--plan-only",
        action="store_true",
        help="Only generate the test plan (Phase 1), do not generate Excel",
    )
    p.add_argument(
        "--from-plan",
        dest="from_plan",
        help="Generate Excel from a confirmed plan.md (Phase 2 only)",
    )
    p.add_argument(
        "--env",
        default=".env",
        help="Path to .env file (default: .env in current directory)",
    )
    p.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose/debug logging",
    )
    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    setup_logging(args.verbose)

    # Load settings
    settings = load_settings(args.env)
    if not settings.llm_api_key:
        print("Error: LLM_API_KEY not set. Configure it in .env file.")
        print("  cp .env.example .env")
        print("  # Edit .env and add your API key")
        return 2

    orch = PipelineOrchestrator(settings)

    # Phase 2 only: from confirmed plan
    if args.from_plan:
        if not args.api:
            print("Error: --api is required when using --from-plan")
            return 2

        state = orch.run_phase2(args.from_plan, args.api)
        if state.errors:
            for err in state.errors:
                print(f"  Error: {err}")
            return 2

        # Write Excel
        try:
            ExcelWriter.write(
                state.interfaces,
                state.single_cases,
                state.biz_flows,
                args.output,
            )
            print(f"\nExcel written to: {args.output}")
            print(f"  Single cases: {len(state.single_cases)}")
            print(f"  Biz flows: {len(state.biz_flows)}")
        except Exception as e:
            print(f"  Error writing Excel: {e}")
            return 2

        return 0

    # Phase 1 or full pipeline
    if args.plan_only:
        if not args.requirement or not args.api:
            print("Error: --requirement and --api are required")
            return 2

        state = orch.run_phase1(args.requirement, args.api)
        if state.errors:
            for err in state.errors:
                print(f"  Error: {err}")
            return 2

        print(f"\nTest plan generated: {state.plan_md_path}")
        print("\nReview the plan, then run:")
        print(f"  python main.py --from-plan {state.plan_md_path} --api {args.api} --output testcase.xlsx")
        return 0

    # Full pipeline
    if not args.requirement or not args.api:
        print("Error: --requirement and --api are required for full pipeline")
        print("  Or use --from-plan to generate from a confirmed plan")
        return 2

    print("Running full pipeline (plan → cases → excel)...")
    state = orch.run_full(args.requirement, args.api, args.output)

    if state.errors:
        for err in state.errors:
            print(f"  Error: {err}")
        return 2

    print(f"\nAll done! Excel written to: {args.output}")
    print(f"  Interfaces: {len(state.interfaces)}")
    print(f"  Single cases: {len(state.single_cases)}")
    print(f"  Biz flows: {len(state.biz_flows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
