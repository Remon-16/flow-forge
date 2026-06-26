"""分批控制器节点 — 插件流水线的测试用例生成。

batch_controller node: runs the plugin-based test case generation pipeline.
"""

import logging
import os
from pathlib import Path

from agents.batch_controller import BatchController
from agents.skeleton_generator import SingleSkeletonGenerator, BizSkeletonGenerator
from graph.state import GraphState
from models.schema import PlanStep, TestPlan
from plugins.loader import load_all_plugins
from plugins.skill_loader import load_skill_extensions
from writers.yaml_writer import YamlWriter

from .helpers import _settings, _knowledge, _sl, save_pipeline_state

logger = logging.getLogger(__name__)


def batch_controller_node(state: GraphState) -> GraphState:
    """运行插件流水线的测试用例生成。

    Run plugin-based test case generation pipeline:
    骨架生成 → 插件执行 → 输出
    """
    state.setdefault("errors", [])

    plan = state.get("plan_parsed")
    interfaces_raw = state.get("interfaces", [])
    output_dir = state.get("output_dir", "./output")
    cases_dir = state.get("cases_dir") or state.get("output_dir", "./output")
    user_guidance = state.get("user_guidance", "")
    batch_size = state.get("batch_size", _settings.batch_size)
    reference_dir = state.get("reference_dir", "")
    api_summary = state.get("api_summary", [])

    # Resume mode: build minimal TestPlan from existing YAMLs
    if state.get("resume") and (plan is None or not interfaces_raw):
        if Path(cases_dir + "/interfaces").is_dir():
            existing_ifaces = YamlWriter.read_interfaces(cases_dir)
        else:
            existing_ifaces = YamlWriter.read_interfaces(output_dir)
        if not interfaces_raw:
            interfaces_raw = existing_ifaces
        if plan is None:
            single_tps = {}
            for iface in existing_ifaces:
                tid = iface.get("test_id", "")
                if tid:
                    single_tps[tid] = [
                        PlanStep(test_id=f"{tid}_positive", description="Positive scenario", tag="P0", scenario_type="positive"),
                        PlanStep(test_id=f"{tid}_negative", description="Negative scenario", tag="P1", scenario_type="negative"),
                        PlanStep(test_id=f"{tid}_boundary", description="Boundary scenario", tag="P2", scenario_type="boundary"),
                    ]
            plan = TestPlan(
                business_summary="Resume mode — minimal plan from existing interfaces",
                single_test_points=single_tps,
            )
        state["plan_parsed"] = plan
        state["interfaces"] = interfaces_raw

    print(_step("case_generation", "pipeline.case_generation"))
    print(_("batch.batch_size", size=batch_size))
    if _sl():
        _sl().log_node_start("batch_controller", "8/10")

    _skills_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'skills', 'builtin')
    _single_exts = load_skill_extensions('skeleton_generator', _settings, _skills_dir)
    _biz_exts = load_skill_extensions('skeleton_generator', _settings, _skills_dir)
    single_skel_gen = SingleSkeletonGenerator(_settings, _knowledge, skill_extensions=_single_exts)
    biz_skel_gen = BizSkeletonGenerator(_settings, _knowledge, skill_extensions=_biz_exts)

    user_module_paths = [
        p.strip() for p in _settings.plugin_modules if p.strip()
    ] if _settings.enable_plugins else []
    plugins = load_all_plugins(_settings, _knowledge, user_module_paths, user_guidance)
    plugin_names = [p.declaration.plugin_name for p in plugins]
    print(_("batch.plugins_loaded", names=plugin_names))

    controller = BatchController(_settings)
    controller._batch_size = batch_size

    api_path = state.get("api_path", "")
    api_doc_text = state.get("api_raw_text", "")
    if not api_doc_text and api_path:
        from doc_parser.text_extractor import extract_text
        try:
            api_doc_text = extract_text(api_path)
        except Exception:
            api_doc_text = ""

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
        )
    except Exception as e:
        msg = f"BatchController failed: {e}"
        logger.exception(msg)
        state["errors"].append(msg)
        print(_("batch.error", msg=msg))
        state["single_cases"] = []
        state["biz_flows"] = []
        state["validation_failures"] = []
        return state

    single_cases = result.get("single_cases", [])
    biz_flows = result.get("biz_flows", [])
    failures = result.get("failures", [])

    state["single_cases"] = single_cases
    state["biz_flows"] = biz_flows
    state["validation_failures"] = failures

    print(_("batch.result", single=len(single_cases), biz=len(biz_flows)))
    if failures:
        print(_("batch.failures_note", count=len(failures), dir=cases_dir))

    # Save pipeline state for resume
    memory_dir = state.get("memory_dir", "")
    if memory_dir:
        save_pipeline_state(memory_dir, "batch_controller")

    if _sl():
        _sl().log_node_end("batch_controller")

    return state
