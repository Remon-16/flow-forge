"""审核节点 — 人工确认和计划修订。

Review nodes: human confirmation interrupt and plan revision.
"""

import json
import logging
from pathlib import Path

from agents.base import BaseAgent
from graph.state import GraphState
from prompts.render import render_prompt

from .helpers import _settings, _sl

logger = logging.getLogger(__name__)


def human_confirm_node(state: GraphState) -> GraphState:
    """中断点 — 暂停执行等待人工审核计划。

    Interrupt point — pauses execution for human review of the plan.
    """
    from langgraph.types import interrupt

    plan_md = state.get("plan_md", "")
    feedback = state.get("plan_feedback", "")

    print(_step("review_plan", "pipeline.review_plan"))
    print("\n" + "=" * 60)
    if feedback:
        print("  " + _("review.revised_from_feedback", feedback=feedback))
    else:
        print("  " + _("review.revised_new"))
    print("=" * 60)
    preview = plan_md[:500] + ("..." if len(plan_md) > 500 else "")
    print(preview)
    print("=" * 60)
    if _sl():
        _sl().log_node_start("human_confirm", "5/9")

    decision = interrupt(_("review.interrupt_title"))

    if decision == "approved":
        state["plan_confirmed"] = True
        state["plan_feedback"] = ""
    else:
        state["plan_confirmed"] = False
        state["plan_feedback"] = decision

    if _sl():
        _sl().log_node_end("human_confirm")

    return state


def revise_plan_node(state: GraphState) -> GraphState:
    """根据用户反馈（文字或批注）修订计划。

    Revise the plan based on user feedback (text or annotations).
    """
    feedback_type = state.get("plan_feedback_type", "text")
    plan_md = state.get("plan_md", "")
    analysis = state.get("requirement_analysis", {})
    api_summary = state.get("api_summary", [])

    if feedback_type == "annotations":
        annotations = state.get("plan_annotations", [])
        if not annotations:
            logger.warning("revise_plan called with annotations type but no annotations data")
            return state
    else:
        feedback = state.get("plan_feedback", "")
        if not feedback.strip():
            logger.warning("revise_plan called without feedback, skipping")
            return state

    agent = BaseAgent(
        api_key=_settings.llm_api_key,
        model=_settings.llm_model,
        temperature=0.3,
        max_tokens=_settings.llm_max_tokens,
        base_url=_settings.llm_base_url,
        rate_limit_delay=_settings.llm_rate_limit_delay,
        retry_base_delay=_settings.llm_retry_base_delay,
        max_concurrency=_settings.llm_max_concurrency,
    )

    if feedback_type == "annotations":
        from prompts.plan_reviser import (
            PLAN_ANNOTATION_REVISER_SYSTEM as system,
            PLAN_ANNOTATION_REVISER_USER as user_msg,
        )
        prompt = render_prompt(
            user_msg,
            original_plan=plan_md,
            annotations=json.dumps(annotations, ensure_ascii=False, indent=2),
            requirement_analysis=str(analysis),
            api_summary=str(api_summary),
        )
        print(_("review.revising_annotation_progress", count=len(annotations)))
    else:
        from prompts.plan_reviser import (
            PLAN_REVISER_SYSTEM as system,
            PLAN_REVISER_USER as user_msg,
        )
        prompt = render_prompt(
            user_msg,
            original_plan=plan_md,
            feedback=state.get("plan_feedback", ""),
            requirement_analysis=str(analysis),
            api_summary=str(api_summary),
        )
        print(_("review.revising_text_progress", model=_settings.llm_model))

    revised = agent.call_llm(prompt, system)
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
