#!/usr/bin/env python3
"""Flow Forge — API Test Case Generation Agent CLI (LangGraph + ReAct).

Usage:
    # Generate test plan only (for human review)
    python main.py --requirement docs/req.md --api docs/api.yaml --plan-only

    # Generate Excel from a confirmed plan
    python main.py --from-plan plan_20260601_120000.md --api docs/api.yaml --output testcase.xlsx

    # Full pipeline with interactive review loop
    python main.py --requirement docs/req.md --api docs/api.yaml --output testcase.xlsx
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from langgraph.errors import GraphInterrupt
from langgraph.types import Command

from agents.excel_writer import ExcelWriter
from config.settings import load_settings
from graph.state import GraphState
from graph.workflow import build_workflow

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


def _save_plan(plan_md: str) -> str:
    """Persist plan markdown to a timestamped file, return path."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = f"plan_{ts}.md"
    Path(path).write_text(plan_md, encoding="utf-8")
    return path


def _run_with_review_loop(graph, initial: GraphState, config: dict) -> GraphState:
    """Run the graph with an interactive review loop at human_confirm.

    When the graph hits the human_confirm interrupt point:
      - Prints a plan summary
      - Asks the user: approve (y) or reject with feedback (n)
      - On reject: resumes with the user's feedback → revise_plan → back to human_confirm
      - On approve: resumes with "approved" → proceeds to parse_plan

    Ctrl+C at any time to abort.
    """
    try:
        result = graph.invoke(initial, config)
    except GraphInterrupt:
        result = None
        print("\n[审核] 计划已生成，等待审核...")

    while True:
        # Check if graph finished
        snapshot = graph.get_state(config)
        if snapshot is None or not snapshot.next:
            break

        # Show plan status
        current_state = snapshot.values or {}
        has_feedback = bool(current_state.get("plan_feedback"))

        # Get user decision
        print()
        choice = input("是否批准此测试计划？(y=批准 / n=提出修改意见): ").strip().lower()

        if choice == "y":
            print("\n计划已批准，继续执行用例生成...")
            try:
                result = graph.invoke(Command(resume="approved"), config)
            except GraphInterrupt:
                # Should not happen on approval, but handle gracefully
                result = graph.invoke(Command(resume="approved"), config)
            break
        elif choice == "n":
            feedback = input("请描述需要修改的内容: ").strip()
            if not feedback:
                print("修改意见不能为空，请重新输入。")
                continue
            print("\n正在根据反馈修改计划...\n")
            try:
                result = graph.invoke(Command(resume=feedback), config)
            except GraphInterrupt:
                # Back at human_confirm with revised plan — loop continues
                print("\n[审核] 计划已修改，请再次审核...")
                continue
            # If no interrupt, graph finished (shouldn't happen but handle)
            break
        else:
            print("无效输入，请输入 y 或 n。")

    return result or {}


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

    # ------------------------------------------------------------------
    # Phase 2 only: from confirmed plan
    # ------------------------------------------------------------------
    if args.from_plan:
        if not args.api:
            print("Error: --api is required when using --from-plan")
            return 2

        plan_path = Path(args.from_plan)
        if not plan_path.exists():
            print(f"Error: plan file not found: {args.from_plan}")
            return 2
        plan_md = plan_path.read_text(encoding="utf-8")

        graph = build_workflow(settings)
        config = {"configurable": {"thread_id": "phase2"}}

        initial: GraphState = {
            "requirement_paths": [],
            "api_path": args.api,
            "output_path": args.output,
            "plan_only": False,
            "requirement_text": "",
            "interfaces": [],
            "plan_md": plan_md,
            "plan_confirmed": True,
        }

        result = graph.invoke(initial, config)

        if result.get("errors"):
            for err in result["errors"]:
                print(f"  Error: {err}")
            return 2

        print(f"\nExcel written to: {args.output}")
        print(f"  Single cases: {len(result.get('single_cases', []))}")
        print(f"  Biz flows: {len(result.get('biz_flows', []))}")
        return 0

    # ------------------------------------------------------------------
    # Phase 1 or full pipeline
    # ------------------------------------------------------------------
    if not args.requirement or not args.api:
        print("Error: --requirement and --api are required")
        return 2

    graph = build_workflow(settings)
    thread_id = f"flow_{datetime.now().strftime('%Y%m%d%H%M%S')}"

    if args.plan_only:
        # Run to generate_plan, then stop (save plan without review loop)
        initial: GraphState = {
            "requirement_paths": list(args.requirement),
            "api_path": args.api,
            "output_path": args.output,
            "plan_only": True,
            "plan_confirmed": True,  # Skip review in plan-only mode
        }
        config = {"configurable": {"thread_id": thread_id}}

        result = graph.invoke(initial, config)
        plan_md = result.get("plan_md", "")
        if not plan_md:
            print("Error: plan generation produced no output")
            return 2

        plan_path = _save_plan(plan_md)
        print(f"\nTest plan generated: {plan_path}")
        print("\nReview the plan, then run:")
        print(f"  python main.py --from-plan {plan_path} --api {args.api} --output testcase.xlsx")
        return 0

    # Full pipeline with interactive review loop
    print("Running full pipeline (plan → review → cases → excel)...")

    initial: GraphState = {
        "requirement_paths": list(args.requirement),
        "api_path": args.api,
        "output_path": args.output,
        "plan_only": False,
    }
    config = {"configurable": {"thread_id": thread_id}}

    result = _run_with_review_loop(graph, initial, config)

    if result.get("errors"):
        for err in result["errors"]:
            print(f"  Error: {err}")
        return 2

    print(f"\nAll done! Excel written to: {args.output}")
    print(f"  Interfaces: {len(result.get('interfaces', []))}")
    print(f"  Single cases: {len(result.get('single_cases', []))}")
    print(f"  Biz flows: {len(result.get('biz_flows', []))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
