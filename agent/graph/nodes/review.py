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
from pathlib import Path
from typing import List, Optional

from graph.state import GraphState
from i18n import _

from . import helpers as _h
from .helpers import _, _step, _sl, save_pipeline_artifact, save_pipeline_state

logger = logging.getLogger(__name__)


# ============================================================================
# Human Confirm Node / 人工审核节点
# ============================================================================


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
    outline = state.get("plan_outline")
    plan_md = state.get("plan_md", "")
    analysis = state.get("requirement_analysis", {})
    api_summary = state.get("api_summary", [])

    # 提取反馈文本 / Extract feedback text
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

    # ---- 路由 / Route ----
    if feedback_type == "annotations":
        revised = _annotation_chunked_revision(state, plan_md, feedback, analysis, api_summary)
    else:
        revised = _text_revision(state, plan_md, feedback, analysis, api_summary)

    # ---- 保存状态 / Save state ----
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
            logger.warning(_("plan_gen.save_error", error=str(e)))

    return state


# ============================================================================
# 共享工具: Section 管理 / Shared Utilities: Section Management
# ============================================================================


def _load_or_parse_sections(
    memory_dir: str, plan_md: str, outline: Optional[dict],
) -> dict:
    """加载 plan_sections.json, 如不存在则解析 plan.md。

    Load saved section structure, or parse plan.md if not available.
    """
    if memory_dir:
        path = Path(memory_dir) / "plan_sections.json"
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                pass
    # 回退: 从 plan.md 解析 / Fallback: parse plan.md
    return _parse_plan_to_sections(plan_md, outline)


def _parse_plan_to_sections(plan_md: str, outline: Optional[dict]) -> dict:
    """从 plan.md 文本解析为 sections 结构 / Parse plan.md into sections.

    按 ## 标题分割为 global、api、biz 三部分, 并映射到 outline 中的 group/flow 名称。
    """
    sections: List[dict] = []
    raw_sections = re.split(r"\n(?=##\s)", plan_md)

    global_parts = []
    api_parts = []
    biz_parts = []

    for sec in raw_sections:
        stripped = sec.strip()
        if not stripped:
            continue
        if stripped.startswith("## 1.") or stripped.startswith("## 4."):
            global_parts.append(stripped)
        elif stripped.startswith("## 2."):
            # 按 ### 分割 / Split by ### subsections
            subs = re.split(r"\n(?=###\s)", stripped)
            for sub in subs:
                sub = sub.strip()
                # 跳过仅含 section 标题的部分 / Skip section header-only parts
                if sub and sub.startswith("###"):
                    api_parts.append(sub)
        elif stripped.startswith("## 3."):
            subs = re.split(r"\n(?=###\s)", stripped)
            for sub in subs:
                sub = sub.strip()
                # 跳过仅含 section 标题的部分 / Skip section header-only parts
                if sub and sub.startswith("###"):
                    biz_parts.append(sub)

    global_content = "\n\n".join(global_parts)

    # 映射 API groups / Map to outline API groups
    api_groups = outline.get("api_groups", []) if outline else []
    group_names = [g.get("group_name", "") for g in api_groups]
    for i, part in enumerate(api_parts):
        # 匹配 outline group name / Match to outline group name
        matched_name = ""
        for name in group_names:
            if name and name in part:
                matched_name = name
                break
        if not matched_name:
            matched_name = f"group_{i}"
        sections.append({
            "key": f"api_{matched_name}",
            "type": "api_group",
            "name": matched_name,
            "content": part,
        })

    # 映射 biz flows / Map to outline biz flows
    biz_flows = outline.get("biz_flows", []) if outline else []
    flow_names = [f.get("name", "") for f in biz_flows]
    for i, part in enumerate(biz_parts):
        matched_name = ""
        for name in flow_names:
            if name and name in part:
                matched_name = name
                break
        if not matched_name:
            matched_name = f"flow_{i}"
        sections.append({
            "key": f"biz_{matched_name}",
            "type": "biz_flow",
            "name": matched_name,
            "content": part,
        })

    return {"global": global_content, "sections": sections}


def _save_plan_sections(memory_dir: str, sections: dict):
    """保存更新后的分块结构 / Save updated section structure."""
    if memory_dir:
        save_pipeline_artifact(memory_dir, "plan_sections.json", sections)


def _find_section_by_key(sections: dict, key: str) -> Optional[dict]:
    """按 key 查找区块 / Find section by key."""
    for sec in sections.get("sections", []):
        if sec.get("key") == key:
            return sec
    return None


def _assemble_plan(sections: dict) -> str:
    """从分块结构拼接完整 plan.md / Assemble plan.md from section structure."""
    parts = [sections.get("global", "")]
    for sec in sections.get("sections", []):
        content = sec.get("content", "")
        if content.strip():
            parts.append(content)
    return "\n\n".join(filter(None, parts))
