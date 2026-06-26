"""计划生成节点 — 基于需求分析和接口定义生成测试计划。

generate_plan node: generates test plan from requirement analysis + interfaces.
"""

import logging
import os
from pathlib import Path

from agents.plan_generator import PlanGenerator
from graph.state import GraphState
from plugins.skill_loader import load_skill_extensions

from .helpers import _settings, _knowledge, _sl, save_pipeline_state, summarize_reference_dir

logger = logging.getLogger(__name__)


def generate_plan_node(state: GraphState) -> GraphState:
    """生成测试计划 Markdown。

    Generate a test plan markdown from requirement analysis + interfaces.
    When reference_dir is set, operates in incremental update mode.
    """
    state.setdefault("errors", [])

    reference_dir = state.get("reference_dir", "")
    reference_summary = summarize_reference_dir(reference_dir)

    _skills_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'skills', 'builtin')
    _exts = load_skill_extensions('plan_generator', _settings, _skills_dir)
    agent = PlanGenerator(_settings, _knowledge, skill_extensions=_exts)

    analysis = state.get("requirement_analysis", {})
    interfaces = state.get("interfaces", [])
    api_summary = state.get("api_summary", [])
    user_guidance = state.get("user_guidance", "")

    if reference_dir:
        print(_step("generate_plan", "pipeline.generate_plan_incremental"))
        print(_("plan.generating_incremental", model=_settings.llm_model, reference_dir=reference_dir))
    else:
        print(_step("generate_plan", "pipeline.generate_plan"))
    print(_("plan.generating", model=_settings.llm_model))
    if _sl():
        _sl().log_node_start("generate_plan", "4/9")

    plan_md = agent.generate(
        analysis, interfaces,
        api_summary=api_summary,
        user_guidance=user_guidance,
        reference_summary=reference_summary,
    )
    state["plan_md"] = plan_md

    # Save plan.md
    memory_dir = state.get("memory_dir", "")
    if memory_dir:
        try:
            plan_path = Path(memory_dir) / "plan.md"
            plan_path.parent.mkdir(parents=True, exist_ok=True)
            plan_path.write_text(plan_md, encoding="utf-8")
        except Exception as e:
            logger.warning("Failed to save plan.md to memory_dir: %s", e)

    plan_len = len(plan_md)
    if _sl():
        plan_path = _sl().save_plan(plan_md)
        print(_("plan.generated_saved", len=plan_len, path=plan_path))
    else:
        print(_("plan.generated", len=plan_len))

    # Save pipeline state for resume (plan.md already saved above)
    if memory_dir:
        save_pipeline_state(memory_dir, "generate_plan")

    if _sl():
        _sl().log_node_end("generate_plan")

    return state
