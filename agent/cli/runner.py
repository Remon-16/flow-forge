"""CLI 运行器 — 主流水线编排。

CLI runner: main pipeline orchestration for all modes.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from config.settings import load_settings
from graph.state import GraphState
from graph.workflow import build_workflow
from i18n import _
from utils.session_logger import SessionLogger

from .bootstrap import ensure_output_structure, make_session_dir, setup_logging
from .interactive import run_interactive
from .parser import build_parser

logger = logging.getLogger(__name__)


def _load_pipeline_state(memory_dir: str) -> dict:
    """从 memory/ 目录加载已保存的流水线中间结果。

    Load saved pipeline artifacts from memory/ directory to reconstruct GraphState.
    Returns a dict of state fields that can be merged into the initial state.
    """
    state: dict = {}
    if not memory_dir:
        return state

    memory_path = Path(memory_dir)

    # 读取进度标记 / Read progress marker
    ps_path = memory_path / "pipeline_state.json"
    completed_stages = []
    if ps_path.exists():
        try:
            with open(ps_path, "r", encoding="utf-8") as f:
                ps = json.load(f)
            completed_stages = ps.get("stages", [])
        except Exception:
            pass

    # 加载各阶段保存的工件 / Load saved artifacts
    def _load_json(filename: str) -> dict | None:
        path = memory_path / filename
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    if "parse_docs" in completed_stages:
        data = _load_json("parsed_docs.json")
        if data:
            state["requirement_text"] = data.get("requirement_text", "")
            state["api_raw_text"] = data.get("api_raw_text", "")
            state["interfaces"] = data.get("interfaces", [])
            state["parse_mode"] = data.get("parse_mode", "raw")

    if "analyze_api" in completed_stages:
        data = _load_json("api_summary.json")
        if data:
            state["api_summary"] = data
            state["api_summary_confirmed"] = True

    if "validate_urls" in completed_stages:
        _load_json("url_validation.json")  # Just validate existence; errors stored in state

    if "analyze_requirement" in completed_stages:
        data = _load_json("requirement_analysis.json")
        if data:
            state["requirement_analysis"] = data

    # plan.md is read by generate_plan_node itself; we set plan_md path
    plan_path = memory_path / "plan.md"
    if plan_path.exists() and "generate_plan" in completed_stages:
        try:
            state["plan_md"] = plan_path.read_text(encoding="utf-8")
        except Exception:
            pass

    if "human_confirm" in completed_stages:
        data = _load_json("review_state.json")
        if data:
            state["plan_confirmed"] = data.get("plan_confirmed", True)

    if "parse_plan" in completed_stages:
        data = _load_json("plan_parsed.json")
        if data:
            state["plan_parsed"] = data

    # Reconstruct interfaces from YAML if available
    cases_dir = state.get("cases_dir", "")
    if cases_dir and "save_interfaces" in completed_stages:
        ifaces_dir = Path(cases_dir) / "interfaces"
        if ifaces_dir.is_dir() and list(ifaces_dir.glob("*.yaml")):
            from writers.yaml_writer import YamlWriter
            try:
                state["interfaces"] = YamlWriter.read_interfaces(str(cases_dir))
            except Exception:
                pass

    return state


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
    # Resume mode: reconstruct state from saved artifacts and continue
    # ------------------------------------------------------------------
    if args.resume:
        output_dir = args.output or settings.output_dir
        output_path = Path(output_dir)
        _cases_dir, _memory_dir = ensure_output_structure(output_path)

        print(_("resume.loading_state", dir=str(_memory_dir)))

        # Load saved pipeline state
        loaded = _load_pipeline_state(str(_memory_dir))

        # If no pipeline_state.json, fall back to legacy resume (batch_controller only)
        ps_path = Path(str(_memory_dir)) / "pipeline_state.json"
        if not ps_path.exists():
            # Legacy fallback: require interfaces for batch-only resume
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
                logger.info("Output directory has existing content, auto-using: %s", output_dir)
                output_path = Path(output_dir)
                _cases_dir, _memory_dir = ensure_output_structure(output_path)

        else:
            logger.info("--resume-overwrite set, will overwrite output directory")

        # Determine resume stage for logging
        next_stage = "batch_controller"
        if ps_path.exists():
            try:
                with open(ps_path, "r", encoding="utf-8") as f:
                    ps = json.load(f)
                from graph.workflow import STAGE_TO_NEXT_NODE
                next_stage = STAGE_TO_NEXT_NODE.get(ps.get("completed_stage", ""), "parse_docs")
            except Exception:
                pass
        print(_("resume.from_stage", stage=next_stage))

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
            "requirement_text": loaded.get("requirement_text", ""),
            "interfaces": loaded.get("interfaces", []),
            "plan_md": loaded.get("plan_md", ""),
            "plan_confirmed": loaded.get("plan_confirmed", True),
            "api_summary_confirmed": loaded.get("api_summary_confirmed", True),
            "api_summary": loaded.get("api_summary", []),
            "requirement_analysis": loaded.get("requirement_analysis", {}),
            "plan_parsed": loaded.get("plan_parsed"),
            "user_guidance": args.prompt or "",
            "parse_mode": args.parse_mode or "raw",
            "parser_path": args.parser_path or "",
            "reference_dir": args.reference_dir or "",
            "resume": True,
            "resume_overwrite": resume_overwrite,
            "auto_mode": args.auto or settings.auto_mode,
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

    auto_mode = args.auto or settings.auto_mode
    if auto_mode:
        print(_("auto.pipeline_start"))

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
        "auto_mode": auto_mode,
    }
    config = {"configurable": {"thread_id": thread_id}}

    if auto_mode:
        result = graph.invoke(initial, config)
    else:
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
