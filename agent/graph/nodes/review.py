"""审核节点 — 人工确认和计划修订。

Review nodes: human confirmation interrupt and plan revision.
Revision uses impact analysis + targeted chunk regeneration.
"""

import json
import logging
from pathlib import Path

from agents.base import BaseAgent
from agents.plan_generator import PlanGenerator, _serialize_interfaces
from graph.state import GraphState
from prompts.plan_reviser import (
    PLAN_REVISION_ANALYSIS_SYSTEM,
    PLAN_REVISION_ANALYSIS_USER,
)
from prompts.render import render_prompt

from . import helpers as _h
from .helpers import _, _step, _sl, save_pipeline_artifact, save_pipeline_state

logger = logging.getLogger(__name__)


def human_confirm_node(state: GraphState) -> GraphState:
    """中断点 — 暂停执行等待人工审核计划。

    Interrupt point — pauses execution for human review of the plan.
    """
    from langgraph.types import interrupt

    plan_md = state.get("plan_md", "")
    feedback = state.get("plan_feedback", "")

    logger.info(_step("review_plan", "pipeline.review_plan"))
    logger.info("\n" + "=" * 60)
    if feedback:
        logger.info("  " + _("review.revised_from_feedback", feedback=feedback))
    else:
        logger.info("  " + _("review.revised_new"))
    logger.info("=" * 60)
    preview = plan_md[:500] + ("..." if len(plan_md) > 500 else "")
    logger.info(preview)
    logger.info("=" * 60)
    if _sl():
        _sl().log_node_start("human_confirm", "7/10")

    if state.get("auto_mode"):
        logger.info(_("auto.plan_approved"))
        state["plan_confirmed"] = True
        state["plan_feedback"] = ""
        memory_dir = state.get("memory_dir", "")
        if memory_dir:
            save_pipeline_artifact(memory_dir, "review_state.json", {"plan_confirmed": True})
            save_pipeline_state(memory_dir, "human_confirm")
        if _sl():
            _sl().log_node_end("human_confirm")
        return state

    decision = interrupt(_("review.interrupt_title"))

    if decision == "approved":
        state["plan_confirmed"] = True
        state["plan_feedback"] = ""
    else:
        state["plan_confirmed"] = False
        state["plan_feedback"] = decision

    # Save review state for resume
    memory_dir = state.get("memory_dir", "")
    if memory_dir and state["plan_confirmed"]:
        save_pipeline_artifact(memory_dir, "review_state.json", {"plan_confirmed": True, "plan_feedback": ""})
        save_pipeline_state(memory_dir, "human_confirm")

    if _sl():
        _sl().log_node_end("human_confirm")

    return state


def revise_plan_node(state: GraphState) -> GraphState:
    """根据用户反馈修订计划 — 影响分析 + 精准重生成。

    Revise the plan using impact analysis + targeted chunk regeneration.
    Works for both text feedback and annotation-based feedback.
    """
    feedback_type = state.get("plan_feedback_type", "text")
    outline = state.get("plan_outline")
    plan_md = state.get("plan_md", "")
    analysis = state.get("requirement_analysis", {})
    api_summary = state.get("api_summary", [])

    if feedback_type == "annotations":
        annotations = state.get("plan_annotations", [])
        if not annotations:
            logger.warning("revise_plan called with annotations type but no annotations data")
            return state
        feedback = json.dumps(annotations, ensure_ascii=False, indent=2)
        logger.info(
            _("review.revising_annotation_progress", count=len(annotations))
        )
    else:
        feedback = state.get("plan_feedback", "")
        if not feedback.strip():
            logger.warning("revise_plan called without feedback, skipping")
            return state
        logger.info(_("review.revising_text_progress", model=_h._settings.llm_model))

    # ========================================================================
    # Step 1: 影响分析 / Impact Analysis
    # ========================================================================
    if outline is None:
        logger.warning("No outline available for revision impact analysis, using full revision")
        return _full_revision_fallback(state, plan_md, feedback, feedback_type)

    impact_agent = BaseAgent(
        api_key=_h._settings.llm_api_key,
        model=_h._settings.llm_model,
        temperature=0.1,
        max_tokens=_h._settings.llm_max_tokens,
        base_url=_h._settings.llm_base_url,
    )

    impact_prompt = render_prompt(
        PLAN_REVISION_ANALYSIS_USER,
        outline=json.dumps(outline, ensure_ascii=False, indent=2),
        feedback=feedback,
    )

    try:
        impact = impact_agent.call_llm_json(impact_prompt, PLAN_REVISION_ANALYSIS_SYSTEM)
    except Exception as e:
        logger.warning("Impact analysis failed: %s, falling back to full revision", e)
        return _full_revision_fallback(state, plan_md, feedback, feedback_type)

    change_summary = impact.get("change_summary", "")
    logger.info("Revision impact: %s", change_summary)

    # ========================================================================
    # Step 2: 按需重新生成 / Targeted Regeneration
    # ========================================================================
    outline_needs_update = impact.get("outline_needs_update", False)
    affected_groups = impact.get("affected_groups", [])
    affected_flows = impact.get("affected_flows", [])

    if outline_needs_update and impact.get("new_outline"):
        outline = impact["new_outline"]
        state["plan_outline"] = outline
        memory_dir = state.get("memory_dir", "")
        if memory_dir:
            save_pipeline_artifact(memory_dir, "plan_outline.json", outline)

    if outline_needs_update or not (affected_groups or affected_flows):
        # 大纲变化或无法确定影响范围 → 全量重新生成
        # Outline changed or uncertain impact → full regeneration
        logger.info("Full plan regeneration required (outline changed or no clear targets)")
        agent = PlanGenerator(_h._settings, _h._knowledge)
        interfaces = state.get("interfaces", [])
        user_guidance = state.get("user_guidance", "")
        revised = agent.generate_from_outline(
            outline=outline,
            requirement_analysis=analysis,
            interfaces=interfaces,
            api_summary=api_summary,
            user_guidance=user_guidance,
        )
    else:
        # 精准重生成 / Targeted regeneration
        revised = _targeted_regenerate(
            state, outline, plan_md, analysis, api_summary,
            affected_groups, affected_flows,
        )

    state["plan_md"] = revised
    state["plan_feedback"] = ""
    state["plan_feedback_type"] = "text"
    state["plan_annotations"] = []

    if _sl():
        _sl().save_plan(revised)

    memory_dir = state.get("memory_dir", "")
    if memory_dir:
        try:
            plan_path = Path(memory_dir) / "plan.md"
            plan_path.parent.mkdir(parents=True, exist_ok=True)
            plan_path.write_text(revised, encoding="utf-8")
        except Exception as e:
            logger.warning("Failed to save revised plan to memory_dir: %s", e)

    return state


# ---------------------------------------------------------------------------
# 辅助函数 / Helpers
# ---------------------------------------------------------------------------

def _full_revision_fallback(
    state: GraphState, plan_md: str, feedback: str, feedback_type: str
) -> GraphState:
    """全量修订回退 / Full revision fallback when outline is unavailable."""
    from prompts.plan_reviser import (
        PLAN_REVISER_SYSTEM,
        PLAN_REVISER_USER,
    )

    analysis = state.get("requirement_analysis", {})
    api_summary = state.get("api_summary", [])

    agent = BaseAgent(
        api_key=_h._settings.llm_api_key,
        model=_h._settings.llm_model,
        temperature=0.3,
        max_tokens=_h._settings.llm_max_tokens,
        base_url=_h._settings.llm_base_url,
    )

    prompt = render_prompt(
        PLAN_REVISER_USER,
        original_plan=plan_md,
        feedback=feedback,
        requirement_analysis=str(analysis),
        api_summary=str(api_summary),
    )

    revised = agent.call_llm(prompt, PLAN_REVISER_SYSTEM)
    state["plan_md"] = revised
    state["plan_feedback"] = ""
    state["plan_feedback_type"] = "text"
    state["plan_annotations"] = []

    memory_dir = state.get("memory_dir", "")
    if memory_dir:
        try:
            plan_path = Path(memory_dir) / "plan.md"
            plan_path.parent.mkdir(parents=True, exist_ok=True)
            plan_path.write_text(revised, encoding="utf-8")
        except Exception as e:
            logger.warning("Failed to save revised plan to memory_dir: %s", e)

    return state


def _targeted_regenerate(
    state: GraphState,
    outline: dict,
    plan_md: str,
    analysis: dict,
    api_summary: list,
    affected_groups: list,
    affected_flows: list,
) -> str:
    """精准重生成受影响的 chunk / Regenerate only affected chunks.

    复用 PlanGenerator 的单 chunk 逻辑。
    Uses the same chunk generation as initial plan generation.
    """
    agent = PlanGenerator(_h._settings, _h._knowledge)
    interfaces = state.get("interfaces", [])
    user_guidance = state.get("user_guidance", "")
    iface_dicts = _serialize_interfaces(interfaces)
    iface_by_id = {d["test_id"]: d for d in iface_dicts if d.get("test_id")}

    # 解析现有 plan.md 为 sections，通过 ## 分割
    # Split existing plan.md into sections by ## headers
    import re
    sections = re.split(r"\n(?=##\s)", plan_md)

    # 保留全局 section (Business Understanding, Mermaid)
    # Keep global sections
    global_sections = []
    api_sections_map = {}
    biz_sections_map = {}
    for sec in sections:
        if sec.startswith("## 1.") or sec.startswith("## 4.") or "Business Understanding" in sec[:80] or "Flowchart" in sec[:80] or "Mermaid" in sec[:80]:
            global_sections.append(sec)
        elif sec.startswith("## 2.") or "Single Interface" in sec[:80]:
            # 通过 outline 映射到 group / Map to group via outline
            for group in outline.get("api_groups", []):
                group_name = group.get("group_name", "")
                if group_name and group_name.lower() in sec.lower():
                    api_sections_map[group_name] = sec
                    break
        elif sec.startswith("## 3.") or "Business Flow" in sec[:80]:
            for flow in outline.get("biz_flows", []):
                flow_name = flow.get("name", "")
                if flow_name and flow_name.lower() in sec.lower():
                    biz_sections_map[flow_name] = sec
                    break

    # 如果 outline 变了，重新生成全局 section / Regenerate global if outline changed
    from prompts.plan_generation import (
        PLAN_CHUNK_GLOBAL_SYSTEM,
        PLAN_CHUNK_GLOBAL_USER,
    )
    import json as _json
    from prompts.render import render_prompt
    from i18n import get_language_name

    outline_json_new = _json.dumps(outline, ensure_ascii=False, indent=2)
    analysis_json = _json.dumps(analysis, ensure_ascii=False, indent=2)
    api_summary_json = _json.dumps(api_summary or [], ensure_ascii=False, indent=2)

    global_prompt = render_prompt(
        PLAN_CHUNK_GLOBAL_USER,
        outline=outline_json_new,
        requirement_analysis=analysis_json,
        api_summary=api_summary_json,
        user_guidance=user_guidance or "(none)",
        reference_summary="(none)",
        language=get_language_name(),
    )
    global_context = agent.call_llm(global_prompt, PLAN_CHUNK_GLOBAL_SYSTEM)

    # 重新生成受影响的 API groups / Regenerate affected API groups
    from prompts.plan_generation import (
        PLAN_CHUNK_API_SECTION_SYSTEM,
        PLAN_CHUNK_API_SECTION_USER,
    )
    for group_name in affected_groups:
        group = next(
            (g for g in outline.get("api_groups", []) if g.get("group_name") == group_name),
            None,
        )
        if not group:
            continue
        api_ids = group.get("api_ids", [])
        group_ifaces = [iface_by_id[aid] for aid in api_ids if aid in iface_by_id]

        prompt = render_prompt(
            PLAN_CHUNK_API_SECTION_USER,
            interface_defs=_json.dumps(group_ifaces, ensure_ascii=False, indent=2),
            user_guidance=user_guidance or "(none)",
            language=get_language_name(),
        )
        system_with_context = render_prompt(
            PLAN_CHUNK_API_SECTION_SYSTEM,
            outline=outline_json_new,
            global_context=global_context,
            group_name=group_name,
            test_focus=group.get("test_focus", ""),
            group_api_ids=_json.dumps(api_ids),
            language=get_language_name(),
        )
        new_section = agent.call_llm(prompt, system_with_context)
        api_sections_map[group_name] = new_section

    # 重新生成受影响的 biz flows / Regenerate affected biz flows
    from prompts.plan_generation import (
        PLAN_CHUNK_BIZ_SECTION_SYSTEM,
        PLAN_CHUNK_BIZ_SECTION_USER,
    )
    for flow_name in affected_flows:
        flow = next(
            (f for f in outline.get("biz_flows", []) if f.get("name") == flow_name),
            None,
        )
        if not flow:
            continue
        api_ids = flow.get("involved_apis", [])
        flow_ifaces = [iface_by_id[aid] for aid in api_ids if aid in iface_by_id]

        prompt = render_prompt(
            PLAN_CHUNK_BIZ_SECTION_USER,
            interface_defs=_json.dumps(flow_ifaces, ensure_ascii=False, indent=2),
            user_guidance=user_guidance or "(none)",
            language=get_language_name(),
        )
        system_with_context = render_prompt(
            PLAN_CHUNK_BIZ_SECTION_SYSTEM,
            outline=outline_json_new,
            global_context=global_context,
            flow_name=flow_name,
            flow_description=flow.get("description", ""),
            flow_api_ids=_json.dumps(api_ids),
            language=get_language_name(),
        )
        new_section = agent.call_llm(prompt, system_with_context)
        biz_sections_map[flow_name] = new_section

    # ========================================================================
    # Step 3: 拼接 / Re-assemble
    # ========================================================================
    parts = [global_context]

    for group in outline.get("api_groups", []):
        group_name = group.get("group_name", "")
        if group_name in api_sections_map:
            parts.append(api_sections_map[group_name])

    for flow in outline.get("biz_flows", []):
        flow_name = flow.get("name", "")
        if flow_name in biz_sections_map:
            parts.append(biz_sections_map[flow_name])

    return "\n\n".join(parts)
