"""CLI 运行器 — 主流水线编排。

CLI runner: main pipeline orchestration for all modes.
"""

import logging
from datetime import datetime
from pathlib import Path

from config.settings import load_settings
from graph.state import GraphState
from graph.workflow import build_workflow
from utils.session_logger import SessionLogger

from .bootstrap import ensure_output_structure, make_session_dir, setup_logging
from .interactive import run_interactive
from .parser import build_parser

logger = logging.getLogger(__name__)


def main() -> int:
    """主入口 — 解析参数、构建工作流并运行。

    Main entry point: parse args, build workflow and run.
    """
    parser = build_parser()
    args = parser.parse_args()
    setup_logging(args.verbose)

    settings = load_settings(args.env)
    if not settings.llm_api_key:
        print(_("cli.no_api_key"))
        return 2

    session_dir = make_session_dir()
    session_logger = SessionLogger(session_dir, debug=args.debug)
    print(_("cli.session_log_dir", path=session_dir.resolve()))

    # ------------------------------------------------------------------
    # Resume mode: skip to batch generation from existing output
    # ------------------------------------------------------------------
    if args.resume:
        output_dir = args.output or settings.output_dir
        output_path = Path(output_dir)
        _cases_dir, _memory_dir = ensure_output_structure(output_path)

        ifaces_dir = _cases_dir / "interfaces"
        if not ifaces_dir.is_dir() or not list(ifaces_dir.glob("*.yaml")):
            old_ifaces_dir = output_path / "interfaces"
            if old_ifaces_dir.is_dir() and list(old_ifaces_dir.glob("*.yaml")):
                print(_("cli.resume_old_structure"))
                ifaces_dir = old_ifaces_dir
            else:
                print(_("cli.resume_no_interfaces", dir=ifaces_dir))
                return 2

        resume_overwrite = args.resume_overwrite
        if not resume_overwrite:
            has_content = output_path.exists() and any(
                p.suffix in (".yaml", ".yml", ".xlsx")
                for p in output_path.rglob("*")
                if p.is_file()
            )
            if has_content:
                base = output_dir
                suffix = 2
                while Path(f"{base}_v{suffix}").exists():
                    suffix += 1
                output_dir = f"{base}_v{suffix}"
                logger.info("输出目录已有内容，自动使用: %s", output_dir)
                output_path = Path(output_dir)
                _cases_dir, _memory_dir = ensure_output_structure(output_path)
        else:
            logger.info("--resume-overwrite 已设置，将覆盖原输出目录")

        graph = build_workflow(settings, session_logger=session_logger)
        config = {"configurable": {"thread_id": f"resume_{datetime.now().strftime('%Y%m%d%H%M%S')}"}}

        initial: GraphState = {
            "requirement_paths": [],
            "api_path": args.api or "",
            "output_path": str(_cases_dir / "test_cases.xlsx"),
            "output_dir": output_dir,
            "cases_dir": str(_cases_dir),
            "memory_dir": str(_memory_dir),
            "debug_snapshots": args.debug_snapshots,
            "output_format": args.output_format or settings.output_format,
            "batch_size": args.batch_size or settings.batch_size,
            "enable_validation": settings.enable_validation,
            "max_validation_retries": settings.max_validation_retries,
            "plan_only": False,
            "requirement_text": "",
            "interfaces": [],
            "plan_md": "",
            "plan_confirmed": True,
            "api_summary_confirmed": True,
            "user_guidance": args.prompt or "",
            "parse_mode": args.parse_mode or "raw",
            "parser_path": args.parser_path or "",
            "reference_dir": args.reference_dir or "",
            "resume": True,
            "resume_overwrite": resume_overwrite,
        }

        result = graph.invoke(initial, config)

        if result.get("errors"):
            for err in result["errors"]:
                print(_("cli.resume_error", error=err))
            session_logger.save_state(dict(result))
            session_logger.log_session_end("failed")
            return 2

        print(_("cli.resume_complete", dir=output_dir, single=len(result.get("single_cases", [])), biz=len(result.get("biz_flows", []))))
        session_logger.save_state(dict(result))
        session_logger.log_session_end("completed")
        return 0

    # ------------------------------------------------------------------
    # Full pipeline
    # ------------------------------------------------------------------
    if not args.requirement or not args.api:
        print(_("cli.requirement_required"))
        return 2

    graph = build_workflow(settings, session_logger=session_logger)
    thread_id = f"flow_{datetime.now().strftime('%Y%m%d%H%M%S')}"

    if args.prompt:
        print(_("cli.user_guidance", guidance=args.prompt))

    output_dir = args.output or settings.output_dir
    cases_dir, memory_dir = ensure_output_structure(Path(output_dir))

    initial: GraphState = {
        "requirement_paths": list(args.requirement),
        "api_path": args.api,
        "output_path": str(cases_dir / "test_cases.xlsx"),
        "output_dir": output_dir,
        "cases_dir": str(cases_dir),
        "memory_dir": str(memory_dir),
        "debug_snapshots": args.debug_snapshots,
        "output_format": args.output_format or settings.output_format,
        "batch_size": args.batch_size or settings.batch_size,
        "enable_validation": settings.enable_validation,
        "max_validation_retries": settings.max_validation_retries,
        "plan_only": False,
        "user_guidance": args.prompt or "",
        "reference_dir": args.reference_dir or "",
        "parse_mode": args.parse_mode,
        "parser_path": args.parser_path or "",
    }
    config = {"configurable": {"thread_id": thread_id}}

    result = run_interactive(graph, initial, config, session_logger)

    if result.get("errors"):
        for err in result["errors"]:
            print(_("cli.pipeline_error", error=err))
        session_logger.save_state(dict(result))
        session_logger.log_session_end("failed")
        return 2

    plan_md = result.get("plan_md", "")
    if plan_md and session_logger:
        session_logger.save_plan(plan_md)

    session_logger.save_state(dict(result))
    session_logger.log_session_end("completed")

    print(_("cli.output_summary", cases_dir=cases_dir, memory_dir=memory_dir, interfaces=len(result.get("interfaces", [])), single=len(result.get("single_cases", [])), biz=len(result.get("biz_flows", [])), session_log=session_dir.resolve() / "session.jsonl"))
    return 0
