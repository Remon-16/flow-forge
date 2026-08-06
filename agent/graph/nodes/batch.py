"""分批控制器节点 — 插件流水线的测试用例生成。

batch_controller node: runs the plugin-based test case generation pipeline.
"""

import logging
import os
from pathlib import Path

from agents.batch_controller import BatchController
from agents.skeleton_generator import SingleSkeletonGenerator, BizSkeletonGenerator
from graph.state import GraphState
from plugins.loader import load_all_plugins
from plugins.skill_loader import load_skill_extensions
from writers.yaml_writer import YamlWriter

from . import helpers as _h
from .helpers import _, _step, _sl, save_pipeline_state

logger = logging.getLogger(__name__)


def batch_controller_node(state: GraphState) -> GraphState:
    """运行插件流水线的测试用例生成。

    Run plugin-based test case generation pipeline:
    骨架生成 → 插件执行 → 输出
    """
    state.setdefault("errors", [])
    # 每次进入节点时重置失败标志，确保成功执行后不会被错误路由到 END / Reset failure flag on every entry to avoid incorrect routing
    state["_batch_failed"] = False

    plan = state.get("plan_parsed")
    interfaces_raw = state.get("interfaces", [])
    output_dir = state.get("output_dir", "./output")
    cases_dir = state.get("cases_dir") or state.get("output_dir", "./output")
    user_guidance = state.get("user_guidance", "")
    batch_size = state.get("batch_size", _h._settings.plugin_batch_size)
    reference_dir = state.get("reference_dir", "")
    api_summary = state.get("api_summary", [])
    case_type = state.get("case_type", "both")

    # Resume mode: restore interfaces from YAML if missing
    # resume 模式：如果接口缺失，从 YAML 恢复
    if state.get("resume") and not interfaces_raw:
        if Path(cases_dir + "/interfaces").is_dir():
            interfaces_raw = YamlWriter.read_interfaces(cases_dir)
        else:
            interfaces_raw = YamlWriter.read_interfaces(output_dir)
        state["interfaces"] = interfaces_raw
        plan = state.get("plan_parsed")

    # plan_parsed 必须存在，否则无法生成用例
    # plan_parsed is required for case generation
    if plan is None:
        msg = _("batch.plan_missing")
        logger.error(msg)
        state["errors"].append(msg)
        # 清空用例列表与异常路径保持一致 / Clear case lists to match exception path
        state["single_cases"] = []
        state["biz_flows"] = []
        state["validation_failures"] = []
        state["_batch_failed"] = True
        return state

    logger.info(_step("case_generation", "pipeline.case_generation"))
    logger.info(_("batch.batch_size", size=batch_size))
    if _sl():
        _sl().log_node_start("batch_controller", "8/10")

    _skills_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'skills', 'builtin')
    _exts = load_skill_extensions('skeleton_generator', _h._settings, _skills_dir)
    single_skel_gen = SingleSkeletonGenerator(_h._settings, _h._knowledge, skill_extensions=_exts)
    biz_skel_gen = BizSkeletonGenerator(_h._settings, _h._knowledge, skill_extensions=_exts)

    user_module_paths = [
        p.strip() for p in _h._settings.plugin_modules if p.strip()
    ] if _h._settings.enable_plugins else []
    plugins = load_all_plugins(_h._settings, _h._knowledge, user_module_paths, user_guidance)
    plugin_names = [p.declaration.plugin_name for p in plugins]
    logger.info(_("batch.plugins_loaded", names=plugin_names))

    controller = BatchController(_h._settings)
    controller._batch_size = batch_size

    api_paths = state.get("api_paths", [])
    api_doc_text = state.get("api_raw_text", "")
    if not api_doc_text and api_paths:
        # 回退：重新提取所有 API 文档文本并合并 / Fallback: re-extract all API doc texts and merge
        from doc_parser.text_extractor import extract_text
        parts = []
        for p in api_paths:
            try:
                parts.append(extract_text(p))
            except Exception:
                pass
        api_doc_text = "\n\n---\n\n".join(parts)

    try:
        result = controller.run(
            plan=plan,
            interfaces=interfaces_raw,
            output_dir=cases_dir,
            single_skel_gen=single_skel_gen,
            biz_skel_gen=biz_skel_gen,
            plugins=plugins,
            user_guidance=user_guidance,
            reference_dir=reference_dir,
            api_doc_text=api_doc_text,
            api_summary=api_summary,
            resume=state.get("resume", False),
            memory_dir=state.get("memory_dir", ""),
            resume_overwrite=state.get("resume_overwrite", False),
            case_type=case_type,
        )
    except Exception as e:
        msg = f"BatchController failed: {e}"
        logger.exception(msg)
        state["errors"].append(msg)
        logger.info(_("batch.aborted", msg=msg))
        state["single_cases"] = []
        state["biz_flows"] = []
        state["validation_failures"] = []
        state["_batch_failed"] = True
        return state

    single_cases = result.get("single_cases", [])
    biz_flows = result.get("biz_flows", [])
    failures = result.get("failures", [])

    state["single_cases"] = single_cases
    state["biz_flows"] = biz_flows
    state["validation_failures"] = failures

    logger.info(_("batch.result", single=len(single_cases), biz=len(biz_flows)))
    if failures:
        logger.info(_("batch.failures_note", count=len(failures), dir=cases_dir))

    # Save pipeline state for resume
    memory_dir = state.get("memory_dir", "")
    if memory_dir:
        save_pipeline_state(memory_dir, "batch_controller")

    if _sl():
        _sl().log_node_end("batch_controller")

    return state
