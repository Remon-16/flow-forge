"""计划生成节点 — 基于轮廓分块生成完整 Markdown 测试计划。

generate_plan node: generates a full Markdown test plan from the outline
using chunked LLM calls (Phase A→B→C→D).
"""

import json
import logging
import os
from pathlib import Path

from agents.plan_generator import PlanGenerator
from graph.state import GraphState
from plugins.skill_loader import load_skill_extensions

from . import helpers as _h
from .helpers import _, _step, _sl, save_pipeline_artifact, save_pipeline_state, summarize_reference_dir

logger = logging.getLogger(__name__)


def generate_plan_node(state: GraphState) -> GraphState:
    """基于轮廓生成完整 Markdown 测试计划。

    Generate the full test plan Markdown from the outline.
    Uses chunked generation when outline has multiple API groups.
    """
    state.setdefault("errors", [])

    reference_dir = state.get("reference_dir", "")
    reference_summary = summarize_reference_dir(reference_dir)

    _skills_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        'skills', 'builtin',
    )
    _exts = load_skill_extensions('plan_generator', _h._settings, _skills_dir)
    agent = PlanGenerator(_h._settings, _h._knowledge, skill_extensions=_exts)

    analysis = state.get("requirement_analysis", {})
    interfaces = state.get("interfaces", [])
    api_summary = state.get("api_summary", [])
    user_guidance = state.get("user_guidance", "")
    outline = state.get("plan_outline")

    if outline is None:
        msg = _("plan.outline_missing")
        logger.error(msg)
        state["errors"].append(msg)
        return state

    if reference_dir:
        logger.info(_step("generate_plan", "pipeline.generate_plan_incremental"))
        logger.info(
            _("plan.generating_incremental",
              model=_h._settings.llm_model, reference_dir=reference_dir)
        )
    else:
        logger.info(_step("generate_plan", "pipeline.generate_plan"))
    logger.info(_("plan.generating", model=_h._settings.llm_model))

    if _sl():
        _sl().log_node_start("generate_plan", "6/10")

    # 加载 chunk progress（resume 时）/ Load chunk progress if resuming
    memory_dir = state.get("memory_dir", "")
    chunk_progress = None
    if memory_dir:
        progress_path = Path(memory_dir) / "plan_chunks_progress.json"
        if progress_path.exists():
            try:
                chunk_progress = json.loads(progress_path.read_text(encoding="utf-8"))
            except Exception:
                pass

    plan_md = agent.generate_from_outline(
        outline=outline,
        requirement_analysis=analysis,
        interfaces=interfaces,
        api_summary=api_summary,
        user_guidance=user_guidance,
        reference_summary=reference_summary,
        chunk_progress=chunk_progress,
    )
    state["plan_md"] = plan_md

    # Save plan.md
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
        logger.info(_("plan.generated_saved", len=plan_len, path=plan_path))
    else:
        logger.info(_("plan.generated", len=plan_len))

    # Save pipeline state for resume
    if memory_dir:
        save_pipeline_state(memory_dir, "generate_plan")

    if _sl():
        _sl().log_node_end("generate_plan")

    return state
