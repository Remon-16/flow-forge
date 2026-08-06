"""审核节点 — 人工确认和计划修订。

Review nodes: human confirmation interrupt and plan revision.
Supports two revision modes:
  - Annotation mode ("r"): 3-phase chunked precise revision (→ review_annotation.py)
  - Text mode ("n"): direct PLAN_REVISER call with impact-analysis fallback (→ review_text.py)

Shared section management utilities used by both revision paths.
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from graph.state import GraphState
from i18n import _
from utils.plan_sections import classify_section, detect_section_level, scan_headings
from flow_forge_schemas.plan_sections import assemble_plan_md, find_section_by_key

from . import helpers as _h
from .helpers import _, _step, _sl, save_pipeline_artifact, save_pipeline_state

logger = logging.getLogger(__name__)


# ============================================================================
# Human Confirm Node / 人工审核节点
# ============================================================================


def human_confirm_node(state: GraphState) -> GraphState:
    """中断点 — 暂停执行等待人工审核计划。

    Interrupt point — pauses execution for human review of the plan.
    plan.md 仅用于展示，不再读取；数据以 plan_sections.json 为准。
    plan.md is for display only; plan_sections.json is authoritative.
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

    memory_dir = state.get("memory_dir", "")

    decision = interrupt(_("review.interrupt_title"))

    if decision == "approved":
        state["plan_confirmed"] = True
        state["plan_feedback"] = ""
        # plan_sections.json 是唯一数据源，审批通过时无需重新加载 plan.md
        # plan_sections.json is the only data source; no need to reload plan.md on approve
    else:
        state["plan_confirmed"] = False
        state["plan_feedback"] = decision
        # 持久化 reject 反馈供 resume 恢复 / Persist rejection feedback for resume recovery
        if memory_dir:
            save_pipeline_artifact(memory_dir, "pending_feedback.json", {
                "plan_feedback": decision,
                "plan_feedback_type": state.get("plan_feedback_type", "text"),
                "plan_annotations": state.get("plan_annotations", []),
            })

    # Save review state for resume — must happen BEFORE archiving feedback
    # 先更新 pipeline 状态，再归档反馈文件（确保崩溃恢复时状态一致）
    memory_dir = state.get("memory_dir", "")
    if memory_dir and state["plan_confirmed"]:
        save_pipeline_artifact(memory_dir, "review_state.json", {"plan_confirmed": True, "plan_feedback": ""})
        save_pipeline_state(memory_dir, "human_confirm")
        # 归档已处理的反馈文件供回溯 / Archive consumed feedback for traceability
        fb_path = Path(memory_dir) / "pending_feedback.json"
        if fb_path.exists():
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            history_dir = Path(memory_dir) / "history-feedback"
            history_dir.mkdir(parents=True, exist_ok=True)
            archive_name = f"pending_feedback_{ts}.json"
            fb_path.rename(history_dir / archive_name)
            logger.info(_("review.feedback_archived_on_approve",
                          path=str(history_dir / archive_name)))

    if _sl():
        _sl().log_node_end("human_confirm")

    return state


# ============================================================================
# Revise Plan Node / 计划修订节点 (路由分发)
# ============================================================================


def revise_plan_node(state: GraphState) -> GraphState:
    """根据用户反馈修订计划 — 路由到批注或文本修订路径。

    Revise the plan based on user feedback.
    Routes to annotation-chunked revision or text revision.
    """
    from .review_annotation import _annotation_chunked_revision
    from .review_text import _text_revision

    feedback_type = state.get("plan_feedback_type", "text")
    analysis = state.get("requirement_analysis", {})
    api_summary = state.get("api_summary", [])

    # 提取反馈文本 / Extract feedback text
    if feedback_type == "annotations":
        annotations = state.get("plan_annotations", [])
        if not annotations:
            logger.warning(_("review.annotations_empty_reprompt"))
            state["plan_feedback"] = ""
            state["plan_annotations"] = []
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

    # ---- 路由 / Route (不再传递 plan_md) ----
    if feedback_type == "annotations":
        revised = _annotation_chunked_revision(state, feedback, analysis, api_summary)
    else:
        revised = _text_revision(state, feedback, analysis, api_summary)

    # ---- 保存状态 / Save state ----
    state["plan_md"] = revised
    state["plan_feedback"] = ""
    state["plan_feedback_type"] = "text"
    state["plan_annotations"] = []

    # 先更新 pipeline 状态 / Update pipeline state
    memory_dir = state.get("memory_dir", "")
    if memory_dir:
        save_pipeline_state(memory_dir, "human_confirm")

    if _sl():
        _sl().save_plan(revised)

    if memory_dir:
        try:
            plan_path = Path(memory_dir) / "plan.md"
            plan_path.parent.mkdir(parents=True, exist_ok=True)
            plan_path.write_text(revised, encoding="utf-8")
            # plan_sections.json 已由 r/n 模式内部更新, 此处不再删除
            # plan_sections.json is updated by r/n mode internally; never deleted
        except Exception as e:
            logger.warning(_("plan_gen.save_error", error=str(e)))

    return state


# ============================================================================
# 共享工具: Section 管理（委托到 utils/plan_sections）/ Shared Utilities: Section Management (delegated to utils/plan_sections)
# _scan_headings / _detect_section_level / _classify_section now imported from utils.plan_sections
# 内部使用脱字号别名保持兼容 / Underscore-prefixed aliases for internal compatibility
# ============================================================================

_scan_headings = scan_headings
_detect_section_level = detect_section_level
_classify_section = classify_section


def _load_or_parse_sections(memory_dir: str) -> dict:
    """加载 plan_sections.json — 唯一数据源。

    Load plan_sections.json — the single source of truth.
    plan.md 不再被读取，数据始终从 plan_sections.json 加载。
    plan.md is no longer read; data always comes from plan_sections.json.
    """
    if memory_dir:
        cache_path = Path(memory_dir) / "plan_sections.json"
        if cache_path.exists():
            try:
                return json.loads(cache_path.read_text(encoding="utf-8"))
            except Exception:
                pass
    # plan_sections.json 不存在时应报错
    # Should error if plan_sections.json doesn't exist
    raise FileNotFoundError(
        f"plan_sections.json not found in {memory_dir}. "
        "The plan generation step must complete before revision."
    )


def _save_plan_sections(memory_dir: str, sections: dict):
    """保存更新后的分块结构 / Save updated section structure."""
    if memory_dir:
        save_pipeline_artifact(memory_dir, "plan_sections.json", sections)
