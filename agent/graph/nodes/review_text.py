"""文本反馈修订 + 影响分析回退路径 / Text feedback revision + impact analysis fallback.

Supports "n" mode (text feedback):
  - Small plans: direct PLAN_REVISER call
  - Large plans: impact analysis + targeted chunk regeneration

Also provides the fallback path when annotation mode can't use plan_sections.json.
"""

import json
import logging

from agents.base import BaseAgent
from agents.plan_generator import PlanGenerator, _serialize_interfaces
from graph.state import GraphState
from i18n import get_language_name, _
from prompts.plan_reviser import (
    PLAN_REVISION_ANALYSIS_SYSTEM,
    PLAN_REVISION_ANALYSIS_USER,
    PLAN_REVISER_SYSTEM,
    PLAN_REVISER_USER,
)
from prompts.render import render_prompt

from . import helpers as _h
from .helpers import _, save_pipeline_artifact
from .review import _parse_plan_to_sections

logger = logging.getLogger(__name__)


# ============================================================================
# 文本反馈修订 / Text Feedback Revision
# ============================================================================


def _text_revision(
    state: GraphState, plan_md: str, feedback: str,
    analysis: dict, api_summary: list,
) -> str:
    """文本反馈修订 — 优先直接修订, 大计划回退影响分析。

    Text revision: use PLAN_REVISER directly for small plans,
    fall back to impact analysis + targeted regeneration for large plans.
    """
    # 渲染 PLAN_REVISER_SYSTEM (修复 {{language}} 遗漏)
    system_rendered = render_prompt(
        PLAN_REVISER_SYSTEM,
        language=get_language_name(),
    )
    prompt = render_prompt(
        PLAN_REVISER_USER,
        original_plan=plan_md,
        feedback=feedback,
        requirement_analysis=str(analysis),
        api_summary=str(api_summary),
    )

    agent = BaseAgent(
        api_key=_h._settings.llm_api_key,
        model=_h._settings.llm_model,
        temperature=0.3,
        max_tokens=_h._settings.llm_max_tokens,
        base_url=_h._settings.llm_base_url,
        context_window=_h._settings.llm_context_window,
        max_output_tokens=_h._settings.llm_max_output_tokens,
    )

    total_tokens = agent._estimate_input_tokens(system_rendered, prompt)
    if total_tokens <= _h._settings.llm_context_window - 4096:
        logger.info(_("review.revising"))
        return agent.call_llm(prompt, system_rendered)

    # 计划过大 → 回退到影响分析 + 分块重生成 / Plan too large → fallback
    logger.info(_("review.text_context_overflow",
                  tokens=total_tokens, window=_h._settings.llm_context_window))
    return _impact_based_revision(state, plan_md, feedback, analysis, api_summary, "text")


# ============================================================================
# 影响分析 + 分块重生成 / Impact Analysis + Chunked Regeneration
# ============================================================================


def _impact_based_revision(
    state: GraphState, plan_md: str, feedback: str,
    analysis: dict, api_summary: list, feedback_type: str,
) -> str:
    """影响分析 + 精准分块重生成 — 大计划回退路径。

    Impact analysis + targeted chunk regeneration fallback for large plans.
    Fixes {{outline}} rendering, passes feedback to chunk generators via
    augmented user_guidance, and fixes flows_list mismatch.
    """
    outline = state.get("plan_outline")

    if outline is None:
        logger.warning(_("review.no_outline_fallback"))
        return _full_revision_fallback(state, plan_md, feedback, feedback_type)

    # Step 1: 影响分析 / Impact analysis
    impact_agent = BaseAgent(
        api_key=_h._settings.llm_api_key,
        model=_h._settings.llm_model,
        temperature=0.1,
        max_tokens=_h._settings.llm_max_tokens,
        base_url=_h._settings.llm_base_url,
    )

    # 渲染 {{outline}} 占位符 / Render {{outline}} placeholder
    impact_system_rendered = render_prompt(
        PLAN_REVISION_ANALYSIS_SYSTEM,
        outline=json.dumps(outline, ensure_ascii=False, indent=2),
    )

    impact_prompt = render_prompt(
        PLAN_REVISION_ANALYSIS_USER,
        outline=json.dumps(outline, ensure_ascii=False, indent=2),
        feedback=feedback,
    )

    try:
        impact = impact_agent.call_llm_json(impact_prompt, impact_system_rendered)
    except Exception as e:
        logger.warning(_("review.impact_analysis_failed", error=str(e)))
        return _full_revision_fallback(state, plan_md, feedback, feedback_type)

    change_summary = impact.get("change_summary", "")
    logger.info(_("review.revision_impact", summary=change_summary))

    # Step 2: 更新 outline (如果需要) / Update outline if needed
    outline_needs_update = impact.get("outline_needs_update", False)
    affected_groups = impact.get("affected_groups", [])
    affected_flows = impact.get("affected_flows", [])

    if outline_needs_update and impact.get("new_outline"):
        outline = impact["new_outline"]
        state["plan_outline"] = outline
        memory_dir = state.get("memory_dir", "")
        if memory_dir:
            save_pipeline_artifact(memory_dir, "plan_outline.json", outline)

    # Step 3: 重新生成 / Regenerate
    if outline_needs_update or not (affected_groups or affected_flows):
        logger.info(_("review.full_regeneration_required"))
        agent = PlanGenerator(_h._settings, _h._knowledge)
        interfaces = state.get("interfaces", [])
        user_guidance = state.get("user_guidance", "")
        augmented = _augment_guidance(user_guidance, feedback, feedback_type)
        revised = agent.generate_from_outline(
            outline=outline,
            requirement_analysis=analysis,
            interfaces=interfaces,
            api_summary=api_summary,
            user_guidance=augmented,
            memory_dir=state.get("memory_dir", ""),
        )
    else:
        revised = _targeted_regenerate(
            state, outline, plan_md, analysis, api_summary,
            affected_groups, affected_flows,
            feedback=feedback,
            feedback_type=feedback_type,
        )

    return revised


def _augment_guidance(user_guidance: str, feedback: str, feedback_type: str) -> str:
    """将修订反馈追加到用户指导中, 供分块生成提示词使用。

    Append revision feedback to user guidance for chunk generation prompts.
    This ensures the LLM knows what changes were requested when regenerating.
    """
    base = user_guidance or "(none)"
    if not feedback:
        return base
    if feedback_type == "annotations":
        return (
            f"{base}\n\n"
            f"## Revision Instructions (from Annotations)\n"
            f"The user reviewed the previous plan and provided the following "
            f"line-level annotations. Apply ONLY the changes that are relevant "
            f"to the content you are generating. Keep everything else identical "
            f"to the previous version.\n\n{feedback}"
        )
    else:
        return (
            f"{base}\n\n"
            f"## Revision Instructions (from User Feedback)\n"
            f"The user reviewed the previous plan and provided this feedback. "
            f"Apply ONLY the changes that are relevant to the content you are "
            f"generating. Keep everything else identical to the previous version."
            f"\n\n{feedback}"
        )


# ============================================================================
# 全量修订回退 / Full Revision Fallback
# ============================================================================


def _full_revision_fallback(
    state: GraphState, plan_md: str, feedback: str, feedback_type: str,
) -> str:
    """全量修订回退 (无 outline 时使用) / Full revision fallback when outline unavailable.

    Fix: renders {{language}} in PLAN_REVISER_SYSTEM before calling LLM.
    """
    analysis = state.get("requirement_analysis", {})
    api_summary = state.get("api_summary", [])

    agent = BaseAgent(
        api_key=_h._settings.llm_api_key,
        model=_h._settings.llm_model,
        temperature=0.3,
        max_tokens=_h._settings.llm_max_tokens,
        base_url=_h._settings.llm_base_url,
        context_window=_h._settings.llm_context_window,
        max_output_tokens=_h._settings.llm_max_output_tokens,
    )

    prompt = render_prompt(
        PLAN_REVISER_USER,
        original_plan=plan_md,
        feedback=feedback,
        requirement_analysis=str(analysis),
        api_summary=str(api_summary),
    )

    # 渲染 PLAN_REVISER_SYSTEM (修复 {{language}} 遗漏)
    system_rendered = render_prompt(
        PLAN_REVISER_SYSTEM,
        language=get_language_name(),
    )
    return agent.call_llm(prompt, system_rendered)


# ============================================================================
# 精准分块重生成 / Targeted Chunk Regeneration
# ============================================================================


def _targeted_regenerate(
    state: GraphState,
    outline: dict,
    plan_md: str,
    analysis: dict,
    api_summary: list,
    affected_groups: list,
    affected_flows: list,
    feedback: str = "",
    feedback_type: str = "text",
) -> str:
    """精准重生成受影响的 chunk / Regenerate only affected chunks.

    修复: {{flows_list}} 参数名不匹配。
    复用 _parse_plan_to_sections 解析现有 plan.md, 消除与 review.py 的重复。
    """
    agent = PlanGenerator(_h._settings, _h._knowledge)
    interfaces = state.get("interfaces", [])
    user_guidance = state.get("user_guidance", "")
    augmented_guidance = _augment_guidance(user_guidance, feedback, feedback_type)
    iface_dicts = _serialize_interfaces(interfaces)
    iface_by_id = {d["test_id"]: d for d in iface_dicts if d.get("test_id")}

    # 复用 _parse_plan_to_sections 解析现有 plan.md / Reuse section parser (dedup)
    parsed = _parse_plan_to_sections(plan_md, outline)

    # 从解析结果构建已有映射 / Build existing section maps from parsed result
    api_sections_map = {}
    biz_sections_map = {}
    for sec in parsed.get("sections", []):
        if sec["type"] == "api_group":
            api_sections_map[sec["name"]] = sec["content"]
        elif sec["type"] == "biz_flow":
            biz_sections_map[sec["name"]] = sec["content"]

    # Regenerate global context / always regenerated for updated context
    from prompts.plan_generation import (
        PLAN_CHUNK_GLOBAL_SYSTEM,
        PLAN_CHUNK_GLOBAL_USER,
    )

    outline_json_new = json.dumps(outline, ensure_ascii=False, indent=2)
    analysis_json = json.dumps(analysis, ensure_ascii=False, indent=2)
    api_summary_json = json.dumps(api_summary or [], ensure_ascii=False, indent=2)

    global_prompt = render_prompt(
        PLAN_CHUNK_GLOBAL_USER,
        outline=outline_json_new,
        requirement_analysis=analysis_json,
        api_summary=api_summary_json,
        user_guidance=augmented_guidance,
        reference_summary="(none)",
        language=get_language_name(),
    )
    global_context = agent.call_llm(
        global_prompt,
        render_prompt(PLAN_CHUNK_GLOBAL_SYSTEM, outline=outline_json_new,
                      language=get_language_name()),
    )

    # Regenerate affected API groups / with feedback injected
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
            interface_defs=json.dumps(group_ifaces, ensure_ascii=False, indent=2),
            user_guidance=augmented_guidance,
            language=get_language_name(),
        )
        system_with_context = render_prompt(
            PLAN_CHUNK_API_SECTION_SYSTEM,
            outline=outline_json_new,
            global_context=global_context,
            group_name=group_name,
            test_focus=group.get("test_focus", ""),
            group_api_ids=json.dumps(api_ids),
            language=get_language_name(),
        )
        api_sections_map[group_name] = agent.call_llm(prompt, system_with_context)

    # Regenerate affected biz flows / Fix: use flows_list format
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
            interface_defs=json.dumps(flow_ifaces, ensure_ascii=False, indent=2),
            user_guidance=augmented_guidance,
            language=get_language_name(),
        )

        # Fix (Root Cause 2): 构造 flows_list 字符串, 匹配模板 {{flows_list}} 占位符
        flows_desc_parts = [
            f"- Name: {flow.get('name', '?')}\n"
            f"  Description: {flow.get('description', '')}\n"
            f"  APIs: {', '.join(flow.get('involved_apis', []))}"
        ]
        flows_list = "\n\n".join(flows_desc_parts)

        system_with_context = render_prompt(
            PLAN_CHUNK_BIZ_SECTION_SYSTEM,
            outline=outline_json_new,
            global_context=global_context,
            flows_list=flows_list,
            language=get_language_name(),
        )
        biz_sections_map[flow_name] = agent.call_llm(prompt, system_with_context)

    # ---- 拼接 / Re-assemble ----
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
