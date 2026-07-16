"""CLI 运行器 — 主流水线编排。

CLI runner: main pipeline orchestration for all modes.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from config.settings import load_settings
from graph.nodes.helpers import load_run_config, save_run_config
from graph.state import GraphState
from graph.workflow import build_workflow
from i18n import _
from utils.session_logger import SessionLogger

from .bootstrap import ensure_output_structure, make_session_dir, setup_logging
from .interactive import run_interactive
from .parser import build_parser

logger = logging.getLogger(__name__)


def _first(*values):
    """返回第一个非 None 值 / Return the first non-None value.

    用于 CLI > saved_config > env.yaml 优先级链。
    Used for CLI > saved_config > env.yaml priority chain.
    """
    for v in values:
        if v is not None:
            return v
    return None


# 配置项与受影响阶段的映射 / Config key to affected stage mapping
_CONFIG_STAGE_DEPENDENCIES: dict = {
    "parse_mode": ["parse_docs"],
    "parser_path": ["parse_docs"],
    "case_type": ["generate_outline", "generate_plan", "parse_plan", "batch_controller"],
    "user_guidance": ["generate_outline", "generate_plan"],
    "plugin_batch_size": ["batch_controller"],
    "output_format": ["write_output"],
    "auto_mode": ["analyze_api", "human_confirm"],
    "reference_dir": ["generate_outline", "generate_plan"],
}

# CLI 参数名到配置键的映射 / CLI arg name to config key mapping
_CLI_ARG_TO_CONFIG_KEY: dict = {
    "case_type": "case_type",
    "prompt": "user_guidance",
    "output_format": "output_format",
    "plugin_batch_size": "plugin_batch_size",
    "auto": "auto_mode",
    "parse_mode": "parse_mode",
    "parser_path": "parser_path",
    "reference_dir": "reference_dir",
    "max_steps": "max_steps",
    "max_retries": "max_retries",
    "skeleton_batch_size": "skeleton_batch_size",
    "plan_single_batch_size": "plan_single_batch_size",
    "case_format_max_retries": "case_format_max_retries",
    "url_doc_match_max_retries": "url_doc_match_max_retries",
    "url_doc_match_strategy": "url_doc_match_strategy",
    "consecutive_batch_failure_limit": "consecutive_batch_failure_limit",
    "max_steps_no_progress": "max_steps_no_progress",
    "url_doc_match_enabled": "url_doc_match_enabled",
    "lang": "lang",
}


def _check_config_overrides(args, saved_config: dict, ps_path: Path) -> None:
    """检查 CLI 参数覆盖是否影响已完成的阶段并发出警告。

    Check if CLI overrides affect already-completed stages and warn.
    When the user provides different CLI args during --resume, some of them
    may target stages that have already finished. This function logs clear
    warnings so the user knows why an override might have no effect.
    """
    if not saved_config or not ps_path.exists():
        return

    try:
        with open(ps_path, "r", encoding="utf-8") as f:
            ps = json.load(f)
    except Exception:
        return

    completed_stages = set(ps.get("stages", []))

    for cli_arg, config_key in _CLI_ARG_TO_CONFIG_KEY.items():
        cli_value = getattr(args, cli_arg, None)
        if cli_value is None or (isinstance(cli_value, str) and not cli_value):
            continue
        saved_value = saved_config.get(config_key)
        if saved_value is not None and str(cli_value) != str(saved_value):
            logger.info(_("resume.cli_override_warning",
                          config_key=config_key,
                          new_value=cli_value,
                          old_value=saved_value))
            affected_stages = _CONFIG_STAGE_DEPENDENCIES.get(config_key, [])
            for stage in affected_stages:
                if stage in completed_stages:
                    logger.info(_("resume.config_override_stale",
                                  config_key=config_key,
                                  stage=stage))


def _load_pipeline_state(memory_dir: str, cases_dir: str = "") -> dict:
    """从 memory/ 目录加载已保存的流水线中间结果。

    Load saved pipeline artifacts from memory/ directory to reconstruct GraphState.
    Returns a dict of state fields that can be merged into the initial state.

    Args:
        memory_dir: 保存了流水线工件的 memory 目录路径。
                    Path to the memory directory with pipeline artifacts.
        cases_dir:  用例输出目录路径（用于从 YAML 重建接口定义）。
                    Path to the cases directory (for YAML interface reconstruction).
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

    # 加载运行配置（第一次运行时保存的 CLI 参数）
    # Load run configuration (CLI args saved during first run)
    run_config = load_run_config(memory_dir)
    if run_config:
        state["_run_config"] = run_config

    # 加载各阶段保存的工件 / Load saved artifacts
    def _load_json(filename: str) -> Optional[dict]:
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
            state["requirement_texts"] = data.get("requirement_texts", [])
            state["api_raw_text"] = data.get("api_raw_text", "")
            state["api_raw_texts"] = data.get("api_raw_texts", [])
            state["interfaces"] = data.get("interfaces", [])
            state["parse_mode"] = data.get("parse_mode", "raw")

    if "analyze_api" in completed_stages:
        data = _load_json("api_summary.json")
        if data:
            # 检查是否有未处理的 API 分析反馈 / Check for pending API analysis feedback
            fb_data = _load_json("api_analysis_feedback.json")
            if fb_data:
                state["api_summary"] = fb_data.get("api_summary", data)
                state["api_summary_feedback"] = fb_data.get("feedback", "")
                state["api_summary_confirmed"] = False
            else:
                state["api_summary"] = data
                state["api_summary_confirmed"] = True

    if "validate_urls" in completed_stages:
        _load_json("url_validation.json")  # Just validate existence; errors stored in state

    if "analyze_requirement" in completed_stages:
        data = _load_json("requirement_analysis.json")
        if data:
            state["requirement_analysis"] = data

    if "generate_outline" in completed_stages:
        data = _load_json("plan_outline.json")
        if data:
            state["plan_outline"] = data

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

    # 加载未处理的计划审核反馈（无论 human_confirm 是否完成都检查）
    # Load pending plan review feedback regardless of human_confirm completion status
    pending_fb = _load_json("pending_feedback.json")
    if pending_fb:
        state["plan_feedback"] = pending_fb.get("plan_feedback", "")
        state["plan_feedback_type"] = pending_fb.get("plan_feedback_type", "text")
        state["plan_annotations"] = pending_fb.get("plan_annotations", [])
        state["plan_confirmed"] = False

    if "parse_plan" in completed_stages:
        data = _load_json("plan_parsed.json")
        if data:
            from models.schema import PlanStep, TestPlan
            # 重建 single_test_points 中的 PlanStep 对象，因为下游通过属性访问
            # Reconstruct PlanStep objects — downstream accesses them via attributes
            single_tps: dict = {}
            for tid, steps in data.get("single_test_points", {}).items():
                single_tps[tid] = [PlanStep(**s) for s in steps]
            state["plan_parsed"] = TestPlan(
                business_summary=data.get("business_summary", ""),
                api_definitions=data.get("api_definitions", []),
                single_test_points=single_tps,
                mermaid_flows=data.get("mermaid_flows", {}),
                biz_flow_scenarios=data.get("biz_flow_scenarios", []),
            )

    # 从 YAML 文件重建接口定义（优先于 parsed_docs.json 中的原始接口）
    # 这样用户在审核阶段手动编辑 YAML 后，resume 时能加载到最新版本
    # Reconstruct interfaces from YAML files (takes priority over original
    # interfaces from parsed_docs.json). This ensures user YAML edits made
    # during the review phase are loaded on resume.
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
    setup_logging(args.verbose, use_stderr=getattr(args, 'studio', False))

    settings = load_settings(args.env)
    if not settings.llm_api_key:
        logger.info(_("cli.no_api_key"))
        return 2

    session_dir = make_session_dir()
    session_logger = SessionLogger(session_dir, debug=args.debug)
    logger.info(_("cli.session_log_dir", path=session_dir.resolve()))

    # ------------------------------------------------------------------
    # Resume mode: reconstruct state from saved artifacts and continue
    # ------------------------------------------------------------------
    if args.resume:
        output_dir = args.output or settings.output_dir
        output_path = Path(output_dir)
        _cases_dir, _memory_dir = ensure_output_structure(output_path)

        # 文件日志（Phase 2）/ File logging setup
        log_to_output = settings.logging_log_to_output
        if getattr(args, 'log_to_output', None) is not None:
            log_to_output = args.log_to_output
        if log_to_output:
            from cli.bootstrap import setup_file_logging
            setup_file_logging(str(output_dir))

        logger.info(_("resume.loading_state", dir=str(_memory_dir)))

        # Load saved pipeline state
        loaded = _load_pipeline_state(str(_memory_dir), str(_cases_dir))

        # 加载已保存的运行配置，与 CLI 参数合并
        # Load saved run config, merge with CLI args
        # 已保存的配置作为默认值，CLI 参数作为覆盖值
        # Saved config as defaults, CLI args as overrides
        saved_config = loaded.pop("_run_config", {})
        if not saved_config:
            logger.info(_("resume.config_missing"))

        # 从已保存配置中提取默认值 / Extract defaults from saved config
        # 使用 _first() 确保 0 和空字符串等合法值不被覆盖
        # Use _first() so legitimate 0/empty values aren't overridden
        _case_type = _first(args.case_type, saved_config.get("case_type"), settings.case_type)
        _output_format = _first(args.output_format, saved_config.get("output_format"), settings.output_format)
        _plugin_batch_size = _first(args.plugin_batch_size, saved_config.get("plugin_batch_size"), settings.plugin_batch_size)
        _auto_mode = _first(args.auto, saved_config.get("auto_mode"), settings.auto_mode)
        _parse_mode = _first(args.parse_mode, saved_config.get("parse_mode"), "raw")
        _user_guidance = _first(args.prompt, saved_config.get("user_guidance"), "")
        _parser_path = _first(args.parser_path, saved_config.get("parser_path"), "")
        _reference_dir = _first(args.reference_dir, saved_config.get("reference_dir"), "")
        _debug_snapshots = _first(args.debug_snapshots, saved_config.get("debug_snapshots"), False)
        _api_paths = list(args.api) if args.api else saved_config.get("api_paths", [])

        # If no pipeline_state.json, fall back to legacy resume (batch_controller only)
        ps_path = Path(str(_memory_dir)) / "pipeline_state.json"
        if not ps_path.exists():
            # Legacy fallback: require interfaces for batch-only resume
            ifaces_dir = _cases_dir / "interfaces"
            if not ifaces_dir.is_dir() or not list(ifaces_dir.glob("*.yaml")):
                old_ifaces_dir = output_path / "interfaces"
                if old_ifaces_dir.is_dir() and list(old_ifaces_dir.glob("*.yaml")):
                    logger.info(_("cli.resume_old_structure"))
                    ifaces_dir = old_ifaces_dir
                else:
                    logger.info(_("cli.resume_no_interfaces", dir=ifaces_dir))
                    return 2

        resume_overwrite = args.resume_overwrite
        if not resume_overwrite and not args.resume:
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
                logger.info(_("cli.output_auto_versioned", dir=output_dir))
                output_path = Path(output_dir)
                _cases_dir, _memory_dir = ensure_output_structure(output_path)

        else:
            logger.info(_("cli.resume_overwrite_enabled"))

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
        logger.info(_("resume.from_stage", stage=next_stage))

        # 检查 CLI 参数覆盖是否影响已完成的阶段 / Warn if overrides affect completed stages
        _check_config_overrides(args, saved_config, ps_path)

        graph = build_workflow(settings, session_logger=session_logger)
        config = {"configurable": {"thread_id": f"resume_{datetime.now().strftime('%Y%m%d%H%M%S')}"}}

        # 保存合并后的运行配置供后续 resume 使用
        # Save merged run config for future resumes
        _merged_config = {
            "case_type": _case_type,
            "user_guidance": _user_guidance,
            "output_format": _output_format,
            "plugin_batch_size": _plugin_batch_size,
            "auto_mode": _auto_mode,
            "parse_mode": _parse_mode,
            "output_dir": output_dir,
            "api_paths": _api_paths,
            "debug_snapshots": _debug_snapshots,
            "parser_path": _parser_path,
            "reference_dir": _reference_dir,
            "resume_overwrite": resume_overwrite,
        }
        save_run_config(str(_memory_dir), _merged_config)

        initial: GraphState = {
            "requirement_paths": [],
            "api_paths": _api_paths,
            "output_path": str(_cases_dir / "test_cases.xlsx"),
            "output_dir": output_dir,
            "cases_dir": str(_cases_dir),
            "memory_dir": str(_memory_dir),
            "debug_snapshots": _debug_snapshots,
            "output_format": _output_format,
            "batch_size": _plugin_batch_size,
            "case_format_enabled": settings.case_format_enabled,
            "case_format_max_retries": settings.case_format_max_retries,
            "plan_only": False,
            "requirement_texts": loaded.get("requirement_texts", []),
            "interfaces": loaded.get("interfaces", []),
            "api_raw_text": loaded.get("api_raw_text", ""),  # 恢复拼接文本供 URL 校验 / Restore merged text for URL validation
            "api_raw_texts": loaded.get("api_raw_texts", []),  # 恢复逐文件原文 / Restore per-file raw texts
            "plan_md": loaded.get("plan_md", ""),
            "plan_confirmed": loaded.get("plan_confirmed", True),
            "api_summary_confirmed": loaded.get("api_summary_confirmed", True),
            "api_summary": loaded.get("api_summary", []),
            "requirement_analysis": loaded.get("requirement_analysis", {}),
            "plan_parsed": loaded.get("plan_parsed"),
            "user_guidance": _user_guidance,
            "parse_mode": _parse_mode,
            "parser_path": _parser_path,
            "reference_dir": _reference_dir,
            "resume": True,
            "resume_overwrite": resume_overwrite,
            "auto_mode": _auto_mode,
            "case_type": _case_type,  # Bug 3 修复: 之前缺失此字段 / Was missing before
        }

        # Bug 1 修复: 如果恢复起始阶段在 human_confirm 之前（含），且非自动模式，
        # 则需要使用 run_interactive() 处理 human_confirm_node 中的 interrupt()
        # Fix: If resuming to a stage at/before human_confirm and not auto mode,
        # use run_interactive() to handle the interrupt() in human_confirm_node
        _PRE_CONFIRM_STAGES = {
            "parse_docs", "analyze_api", "validate_interface_urls",
            "save_interfaces", "analyze_requirement", "generate_outline",
            "generate_plan", "human_confirm",
        }
        if next_stage in _PRE_CONFIRM_STAGES and not _auto_mode:
            if getattr(args, 'studio', False):
                from cli.studio_bridge import run_studio_protocol
                logger.info(_("resume.interactive_mode", stage=next_stage))
                result = run_studio_protocol(graph, initial, config, session_logger)
            else:
                logger.info(_("resume.interactive_mode", stage=next_stage))
                result = run_interactive(graph, initial, config, session_logger)
        else:
            result = graph.invoke(initial, config)

        if result.get("errors"):
            for err in result["errors"]:
                logger.info(_("cli.resume_error", error=err))
            session_logger.save_state(dict(result))
            session_logger.log_session_end("failed")
            return 2

        logger.info(_("cli.resume_complete", dir=output_dir, single=len(result.get("single_cases", [])), biz=len(result.get("biz_flows", []))))
        session_logger.save_state(dict(result))
        session_logger.log_session_end("completed")
        return 0

    # ------------------------------------------------------------------
    # Full pipeline
    # ------------------------------------------------------------------
    if not args.requirement or not args.api:
        logger.info(_("cli.requirement_required"))
        return 2

    auto_mode = _first(args.auto, settings.auto_mode)
    if auto_mode:
        logger.info(_("auto.pipeline_start"))

    graph = build_workflow(settings, session_logger=session_logger)
    thread_id = f"flow_{datetime.now().strftime('%Y%m%d%H%M%S')}"

    if args.prompt:
        logger.info(_("cli.user_guidance", guidance=args.prompt))

    # --- 解析 CLI 对校验和语言等配置的覆盖 / Resolve CLI overrides ---
    # 用例格式校验开关 / Case format validation toggle
    if args.no_validation:
        _case_format_enabled = False
    elif args.validation:
        _case_format_enabled = True
    else:
        _case_format_enabled = settings.case_format_enabled

    # URL 文档匹配校验开关 / URL doc-match validation toggle
    if args.no_url_doc_match_enabled:
        _url_doc_match_enabled = False
    elif args.url_doc_match_enabled:
        _url_doc_match_enabled = True
    else:
        _url_doc_match_enabled = settings.url_doc_match_enabled

    # 语言设置 / Language setting
    if args.lang is not None:
        import os as _os
        _os.environ["AGENT_LANG"] = args.lang

    output_dir = args.output or settings.output_dir
    cases_dir, memory_dir = ensure_output_structure(Path(output_dir))

    # 文件日志（Phase 2）/ File logging setup
    log_to_output = settings.logging_log_to_output
    if getattr(args, 'log_to_output', None) is not None:
        log_to_output = args.log_to_output
    if log_to_output:
        from cli.bootstrap import setup_file_logging
        setup_file_logging(str(output_dir))

    initial: GraphState = {
        "requirement_paths": list(args.requirement),
        "api_paths": list(args.api) if args.api else [],
        "output_path": str(cases_dir / "test_cases.xlsx"),
        "output_dir": output_dir,
        "cases_dir": str(cases_dir),
        "memory_dir": str(memory_dir),
        "debug_snapshots": args.debug_snapshots,
        "output_format": _first(args.output_format, settings.output_format),
        "batch_size": _first(args.plugin_batch_size, settings.plugin_batch_size),
        "case_format_enabled": _case_format_enabled,
        "case_format_max_retries": _first(args.case_format_max_retries, settings.case_format_max_retries),
        "plan_only": False,
        "user_guidance": _first(args.prompt, ""),
        "reference_dir": _first(args.reference_dir, ""),
        "parse_mode": args.parse_mode,
        "parser_path": _first(args.parser_path, ""),
        "auto_mode": auto_mode,
        "case_type": _first(args.case_type, settings.case_type),
    }
    config = {"configurable": {"thread_id": thread_id}}

    # 保存运行配置供后续 resume 使用
    # Save run config for future resume
    _run_config = {
        "case_type": _first(args.case_type, settings.case_type),
        "user_guidance": _first(args.prompt, ""),
        "output_format": _first(args.output_format, settings.output_format),
        "plugin_batch_size": _first(args.plugin_batch_size, settings.plugin_batch_size),
        "auto_mode": auto_mode,
        "parse_mode": args.parse_mode,
        "output_dir": output_dir,
        "api_paths": list(args.api) if args.api else [],
        "requirement_paths": list(args.requirement),
        "debug_snapshots": args.debug_snapshots,
        "parser_path": _first(args.parser_path, ""),
        "reference_dir": _first(args.reference_dir, ""),
    }
    save_run_config(str(memory_dir), _run_config)

    if auto_mode:
        result = graph.invoke(initial, config)
    elif getattr(args, 'studio', False):
        from cli.studio_bridge import run_studio_protocol
        result = run_studio_protocol(graph, initial, config, session_logger)
    else:
        result = run_interactive(graph, initial, config, session_logger)

    if result.get("errors"):
        for err in result["errors"]:
            logger.info(_("cli.pipeline_error", error=err))
        session_logger.save_state(dict(result))
        session_logger.log_session_end("failed")
        return 2

    plan_md = result.get("plan_md", "")
    if plan_md and session_logger:
        session_logger.save_plan(plan_md)

    session_logger.save_state(dict(result))
    session_logger.log_session_end("completed")

    logger.info(_("cli.output_summary", cases_dir=cases_dir, memory_dir=memory_dir, interfaces=len(result.get("interfaces", [])), single=len(result.get("single_cases", [])), biz=len(result.get("biz_flows", [])), session_log=session_dir.resolve() / "session.jsonl"))
    return 0
