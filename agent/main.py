#!/usr/bin/env python3
"""Flow Forge — API Test Case Generation Agent CLI (LangGraph + ReAct).

Usage:
    # Generate test plan only (for human review)
    python main.py --requirement docs/req.md --api docs/api.yaml --plan-only

    # Generate Excel from a confirmed plan
    python main.py --from-plan plan_20260601_120000.md --api docs/api.yaml --output testcase.xlsx

    # Full pipeline with interactive review loop
    python main.py --requirement docs/req.md --api docs/api.yaml --output testcase.xlsx

    # With user guidance injected into plan/case generation
    python main.py --requirement docs/req.md --api docs/api.yaml \\
        --prompt "关注 VIP 用户的折扣逻辑和节假日特殊定价" --output testcase.xlsx

    # With debug logging (full LLM I/O written to session debug.log)
    python main.py --requirement docs/req.md --api docs/api.yaml --debug

    # Parse modes for API docs:
    #   raw (default): pass raw text to ApiAnalyzer LLM
    #   rule: use built-in OpenAPI/Markdown parser
    #   llm : pre-extract structured interfaces via LLM
    python main.py --requirement docs/req.md --api docs/api.docx --parse-mode raw
    python main.py --requirement docs/req.md --api docs/api.yaml --parse-mode rule
    python main.py --requirement docs/req.md --api docs/api.md --parse-mode llm

    # Use a custom parser
    python main.py --requirement docs/req.md --api docs/api.yaml \\
        --parse-mode rule --parser-path my_parser.py
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from langgraph.errors import GraphInterrupt
from langgraph.types import Command

from config.settings import load_settings
from graph.nodes import revise_plan_node
from graph.state import GraphState
from graph.workflow import build_workflow
from utils.session_logger import SessionLogger

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(level=level, format=fmt, datefmt="%H:%M:%S")


def _make_session_dir() -> Path:
    """Create a timestamped session directory under logs/."""
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    session_dir = Path("logs") / ts
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


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
        help="Output Excel file path (used when output-format includes excel)",
    )
    p.add_argument(
        "--output-dir",
        default="",
        help="YAML output root directory (default: ./output, or from .env)",
    )
    p.add_argument(
        "--output-format",
        choices=["yaml", "excel", "both"],
        default="",
        help="Output format: yaml, excel, or both (default: both, or from .env)",
    )
    p.add_argument(
        "--batch-size",
        type=int,
        default=0,
        help="Max cases per generation batch (default: 10, or from .env)",
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
        "--prompt", "-p",
        default="",
        help="User guidance injected into plan and case generation prompts",
    )
    p.add_argument(
        "--env",
        default=".env",
        help="Path to .env file (default: .env in current directory)",
    )
    p.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose/debug console logging",
    )
    p.add_argument(
        "--debug",
        action="store_true",
        help="Enable detailed debug logging (full LLM I/O written to session debug.log)",
    )
    p.add_argument(
        "--parse-mode", "-m",
        choices=["raw", "rule", "llm"],
        default="raw",
        help="API document parse mode (default: raw). "
             "raw = pass text to ApiAnalyzer LLM; "
             "rule = use built-in/custom rule parser; "
             "llm = pre-extract structured interfaces via LLM",
    )
    p.add_argument(
        "--parser-path",
        default="",
        help="Path to custom parser .py file (only for --parse-mode rule). "
             "Must implement: parse(file_path: str) -> List[InterfaceDef]",
    )
    p.add_argument(
        "--reference-dir",
        default="",
        help="Reference directory for incremental updates. The system scans "
             "this directory for existing plans, interfaces, and cases, and "
             "generates a plan that only covers new or changed scenarios.",
    )
    p.add_argument(
        "--resume",
        action="store_true",
        help="Resume batch generation from existing output_dir. Skips "
             "document parsing and plan generation. Use with --output-dir.",
    )
    return p


def _run_interactive(
    graph,
    initial: GraphState,
    config: dict,
    session_logger: SessionLogger | None = None,
) -> GraphState:
    """Run the graph handling all interrupt points.

    Two types of interrupts exist:
      - analyze_api: Optional — triggered only when critical uncertainties found.
        User may provide feedback or skip.
      - human_confirm: Mandatory — always triggered. User must approve (y) or
        reject with feedback (n).

    Ctrl+C at any time to abort.
    """

    def _resume(value):
        try:
            return graph.invoke(Command(resume=value), config)
        except GraphInterrupt:
            return None

    # Initial invocation
    print("\n[开始] Flow Forge 智能体流水线启动...")
    if session_logger:
        session_logger.log_event("pipeline_start", stage="interactive")

    try:
        result = graph.invoke(initial, config)
    except GraphInterrupt:
        result = None

    while True:
        snapshot = graph.get_state(config)
        if snapshot is None or not snapshot.next:
            break

        pending = snapshot.next[0] if snapshot.next else ""

        if pending == "analyze_api":
            # Optional interrupt for API analysis clarifications
            choice = input(
                "\n是否需要澄清以上问题？(输入修改意见 / skip 跳过): "
            ).strip()
            if choice.lower() == "skip":
                result = _resume("skip")
            elif choice:
                result = _resume(choice)
            else:
                result = _resume("skip")

        elif pending == "human_confirm":
            # Mandatory interrupt for plan review
            choice = input(
                "\n是否批准此测试计划？\n"
                "  y = 批准，继续执行用例生成\n"
                "  n = 提出文字修改意见\n"
                "  r = 按批注文件修改（需先在 case-editor 中对 plan.md 添加批注）\n"
                "请输入 (y/n/r): "
            ).strip().lower()
            if choice == "y":
                print("\n计划已批准，继续执行用例生成...")
                result = _resume("approved")
            elif choice == "n":
                feedback = input("请描述需要修改的内容: ").strip()
                if not feedback:
                    print("修改意见不能为空，请重新输入。")
                    continue
                print("\n正在根据反馈修改计划...\n")

                # 不通过图的 interrupt/routing 机制处理拒绝。
                # 直接获取当前 state、调用 revise_plan_node 修订，
                # 然后 update_state 写回 checkpoint。
                snapshot = graph.get_state(config)
                state = dict(snapshot.values)
                state["plan_feedback"] = feedback
                state["plan_feedback_type"] = "text"
                state["plan_confirmed"] = False
                revised_state = revise_plan_node(state)
                graph.update_state(config, revised_state, as_node="revise_plan")

                print("\n[审核] 计划已修改，请再次审核...")
                # 继续 while 循环，下一轮显示 human_confirm 待处理
            elif choice == "r":
                import json as _json
                snapshot = graph.get_state(config)
                state = dict(snapshot.values)
                output_dir = state.get("output_dir", "./output")
                comments_path = Path(output_dir) / "plan_comments.json"

                if not comments_path.exists():
                    print(f"\n错误: 未找到批注文件: {comments_path.resolve()}")
                    print("请先在 case-editor 中对测试计划添加批注。")
                    continue

                try:
                    annotations = _json.loads(comments_path.read_text("utf-8"))
                except Exception as e:
                    print(f"\n错误: 批注文件解析失败: {e}")
                    continue

                if not annotations:
                    print("\n错误: 批注文件为空，请添加批注后重试。")
                    continue

                print(f"\n已读取 {len(annotations)} 条批注:")
                for i, ann in enumerate(annotations[:5], 1):
                    print(f"  {i}. [行{ann.get('line_number', '?')}] {ann.get('review_comment', '')[:60]}")
                if len(annotations) > 5:
                    print(f"  ... 共 {len(annotations)} 条")

                print("\n正在根据批注修改计划...\n")

                state["plan_feedback_type"] = "annotations"
                state["plan_annotations"] = annotations
                state["plan_confirmed"] = False
                revised_state = revise_plan_node(state)
                graph.update_state(config, revised_state, as_node="revise_plan")

                # 归档批注文件
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                history_dir = Path(output_dir) / "history-comments"
                history_dir.mkdir(parents=True, exist_ok=True)
                archive_name = f"plan_comments_{ts}.json"
                comments_path.rename(history_dir / archive_name)
                print(f"批注文件已归档: history-comments/{archive_name}")

                print("\n[审核] 计划已修改，请再次审核...")
            else:
                print("无效输入，请输入 y、n 或 r。")
        else:
            break

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
    # Setup session directory + logger
    # ------------------------------------------------------------------
    session_dir = _make_session_dir()
    session_logger = SessionLogger(session_dir, debug=args.debug)
    print(f"[Session] 日志目录: {session_dir.resolve()}")

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

        graph = build_workflow(settings, session_logger=session_logger)
        config = {"configurable": {"thread_id": "phase2"}}

        initial: GraphState = {
            "requirement_paths": [],
            "api_path": args.api,
            "output_path": args.output,
            "output_dir": args.output_dir or settings.output_dir,
            "output_format": args.output_format or settings.output_format,
            "batch_size": args.batch_size or settings.batch_size,
            "enable_validation": settings.enable_validation,
            "max_validation_retries": settings.max_validation_retries,
            "plan_only": False,
            "requirement_text": "",
            "interfaces": [],
            "plan_md": plan_md,
            "plan_confirmed": True,
            "api_summary_confirmed": True,
            "user_guidance": args.prompt or "",
            "parse_mode": args.parse_mode,
            "parser_path": args.parser_path or "",
            "reference_dir": args.reference_dir or "",
        }

        result = graph.invoke(initial, config)

        if result.get("errors"):
            for err in result["errors"]:
                print(f"  Error: {err}")
            session_logger.log_session_end("failed")
            return 2

        print(f"\nExcel written to: {args.output}")
        print(f"  Single cases: {len(result.get('single_cases', []))}")
        print(f"  Biz flows: {len(result.get('biz_flows', []))}")
        session_logger.save_state(dict(result))
        session_logger.log_session_end("completed")
        return 0

    # ------------------------------------------------------------------
    # Resume mode: skip to batch generation from existing output_dir
    # ------------------------------------------------------------------
    if args.resume:
        output_dir = args.output_dir or settings.output_dir
        ifaces_dir = Path(output_dir) / "interfaces"
        if not ifaces_dir.is_dir() or not list(ifaces_dir.glob("*.yaml")):
            print(f"Error: 未在 {ifaces_dir} 中找到接口 YAML 文件")
            print("  --resume 需要已有接口定义的 output 目录")
            return 2

        plan_md = ""
        if args.from_plan:
            plan_path = Path(args.from_plan)
            if not plan_path.exists():
                print(f"Error: plan file not found: {args.from_plan}")
                return 2
            plan_md = plan_path.read_text(encoding="utf-8")

        graph = build_workflow(settings, session_logger=session_logger)
        config = {"configurable": {"thread_id": f"resume_{datetime.now().strftime('%Y%m%d%H%M%S')}"}}

        initial: GraphState = {
            "requirement_paths": [],
            "api_path": args.api or "",
            "output_path": args.output or "",
            "output_dir": output_dir,
            "output_format": args.output_format or settings.output_format,
            "batch_size": args.batch_size or settings.batch_size,
            "enable_validation": settings.enable_validation,
            "max_validation_retries": settings.max_validation_retries,
            "plan_only": False,
            "requirement_text": "",
            "interfaces": [],
            "plan_md": plan_md,
            "plan_confirmed": True,
            "api_summary_confirmed": True,
            "user_guidance": args.prompt or "",
            "parse_mode": args.parse_mode or "raw",
            "parser_path": args.parser_path or "",
            "reference_dir": args.reference_dir or "",
            "resume": True,
        }

        result = graph.invoke(initial, config)

        if result.get("errors"):
            for err in result["errors"]:
                print(f"  Error: {err}")
            session_logger.save_state(dict(result))
            session_logger.log_session_end("failed")
            return 2

        print(f"\nResume complete. Output in: {output_dir}")
        print(f"  Single cases: {len(result.get('single_cases', []))}")
        print(f"  Biz flows: {len(result.get('biz_flows', []))}")
        session_logger.save_state(dict(result))
        session_logger.log_session_end("completed")
        return 0

    # ------------------------------------------------------------------
    # Phase 1 or full pipeline
    # ------------------------------------------------------------------
    if not args.requirement or not args.api:
        print("Error: --requirement and --api are required")
        return 2

    graph = build_workflow(settings, session_logger=session_logger)
    thread_id = f"flow_{datetime.now().strftime('%Y%m%d%H%M%S')}"

    if args.plan_only:
        # Run to generate_plan, then stop (save plan without review loop)
        initial: GraphState = {
            "requirement_paths": list(args.requirement),
            "api_path": args.api,
            "output_path": args.output,
            "output_dir": args.output_dir or settings.output_dir,
            "output_format": args.output_format or settings.output_format,
            "batch_size": args.batch_size or settings.batch_size,
            "enable_validation": settings.enable_validation,
            "max_validation_retries": settings.max_validation_retries,
            "plan_only": True,
            "plan_confirmed": True,  # Skip review in plan-only mode
            "user_guidance": args.prompt or "",
            "parse_mode": args.parse_mode,
            "parser_path": args.parser_path or "",
            "reference_dir": args.reference_dir or "",
        }
        config = {"configurable": {"thread_id": thread_id}}

        result = graph.invoke(initial, config)
        plan_md = result.get("plan_md", "")
        if not plan_md:
            print("Error: plan generation produced no output")
            session_logger.log_session_end("failed")
            return 2

        # Save to session dir
        plan_path = session_logger.save_plan(plan_md)
        session_logger.save_state(dict(result))

        print(f"\nTest plan generated: {plan_path.resolve()}")
        print("\nReview the plan, then run:")
        print(f"  python main.py --from-plan {plan_path.resolve()} --api {args.api} --output testcase.xlsx")
        session_logger.log_session_end("completed")
        return 0

    # Full pipeline with interactive review loop
    if args.prompt:
        print(f"[Prompt] 用户指导: {args.prompt}")

    initial: GraphState = {
        "requirement_paths": list(args.requirement),
        "api_path": args.api,
        "output_path": args.output,
        "output_dir": args.output_dir or settings.output_dir,
        "output_format": args.output_format or settings.output_format,
        "batch_size": args.batch_size or settings.batch_size,
        "enable_validation": settings.enable_validation,
        "max_validation_retries": settings.max_validation_retries,
        "plan_only": False,
        "user_guidance": args.prompt or "",
        "reference_dir": args.reference_dir or "",
    }
    config = {"configurable": {"thread_id": thread_id}}

    result = _run_interactive(graph, initial, config, session_logger)

    if result.get("errors"):
        for err in result["errors"]:
            print(f"  Error: {err}")
        session_logger.save_state(dict(result))
        session_logger.log_session_end("failed")
        return 2

    # Ensure plan is saved in session directory
    plan_md = result.get("plan_md", "")
    if plan_md and session_logger:
        session_logger.save_plan(plan_md)

    session_logger.save_state(dict(result))
    session_logger.log_session_end("completed")

    print(f"\nAll done! Excel written to: {args.output}")
    print(f"  Interfaces: {len(result.get('interfaces', []))}")
    print(f"  Single cases: {len(result.get('single_cases', []))}")
    print(f"  Biz flows: {len(result.get('biz_flows', []))}")
    print(f"  Session log: {session_dir.resolve() / 'session.jsonl'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
