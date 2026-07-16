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
from utils.plan_sections import classify_section, detect_section_level, scan_headings

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

    # 打印 plan.md 路径, 方便用户手动编辑 / Print plan.md path for manual editing
    memory_dir = state.get("memory_dir", "")
    if memory_dir:
        plan_path = Path(memory_dir) / "plan.md"
        if plan_path.exists():
            logger.info(_("review.manual_edit_hint", path=str(plan_path.resolve())))

    decision = interrupt(_("review.interrupt_title"))

    if decision == "approved":
        state["plan_confirmed"] = True
        state["plan_feedback"] = ""
        # 从磁盘重新加载 plan.md (含用户手动编辑) / Reload plan.md from disk
        if memory_dir:
            plan_path = Path(memory_dir) / "plan.md"
            if plan_path.exists():
                try:
                    disk_content = plan_path.read_text(encoding="utf-8")
                    if disk_content.strip():
                        state["plan_md"] = disk_content
                        logger.info(_("review.reloaded_from_disk", path=str(plan_path.resolve())))
                except Exception as e:
                    logger.warning(_("review.reload_error", error=str(e)))
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


def _load_or_parse_sections(
    memory_dir: str, plan_md: str, outline: Optional[dict],
) -> dict:
    """加载 plan_sections.json, 如过期或不存在则解析 plan.md。

    Load saved section structure; if stale or missing, parse plan.md instead.
    """
    if memory_dir:
        cache_path = Path(memory_dir) / "plan_sections.json"
        if cache_path.exists():
            plan_path = Path(memory_dir) / "plan.md"
            # plan.md 比缓存新 → 缓存过期, 重新解析
            # plan.md newer than cache → stale, re-parse from plan.md
            if (not plan_path.exists()
                    or cache_path.stat().st_mtime >= plan_path.stat().st_mtime):
                try:
                    return json.loads(cache_path.read_text(encoding="utf-8"))
                except Exception:
                    pass
    return _parse_plan_to_sections(plan_md, outline)


def _parse_plan_to_sections(plan_md: str, outline: Optional[dict]) -> dict:
    """从 plan.md 文本解析为 sections 结构 / Parse plan.md into sections.

    自适应标题级别 — 不硬编码 ## 或 ###。
    Heading-level adaptive — no hard-coded ## or ### levels.

    流程 / Flow:
    1. _detect_section_level() 检测主分段级别 L
    2. 按 #{L} 标题切分文档 / Split document by #{L} headings
    3. 用关键词分类每个区块 (global / api_group / biz_flow)
    4. 区块内部按 #{L+1,} 标题拆分并映射到 outline
    """
    sections: List[dict] = []

    section_level = _detect_section_level(plan_md)
    subsplit_level = section_level + 1

    raw_parts = re.split(rf"\n(?=#{{{section_level}}}\s)", plan_md)

    # 第一个 part 是 section_level 标题之前的内容, 归入 global 前导文本
    # First part is content before the first section_level heading → global preamble
    global_preamble = ""

    api_parts: List[str] = []
    biz_parts: List[str] = []
    global_parts: List[str] = []

    for i, part in enumerate(raw_parts):
        stripped = part.strip()
        if not stripped:
            continue

        # 提取该 part 的首个标题行用于分类
        # Extract first heading line of this part for classification
        first_line = stripped.split("\n", 1)[0].strip()
        heading_match = re.match(r"^#{1,6}\s+(.+)", first_line)
        heading_text = heading_match.group(1) if heading_match else ""
        part_level = len(heading_match.group(0).split()[0]) if heading_match else 0

        # 跳过不是以 section_level 标题开头的 part (前导内容)
        # Skip parts that don't start with section_level heading (preamble)
        if part_level != section_level and i == 0:
            global_preamble = stripped
            continue

        sec_type = _classify_section(heading_text)

        if sec_type == "global":
            global_parts.append(stripped)
        elif sec_type == "api":
            # 按 #{subsplit_level,} 标题拆分子区块
            # Split by #{subsplit_level,} headings into subsections
            subs = re.split(rf"\n(?=#{{{subsplit_level},}}\s)", stripped)
            for sub in subs:
                sub = sub.strip()
                if sub:
                    api_parts.append(sub)
        elif sec_type == "biz":
            subs = re.split(rf"\n(?=#{{{subsplit_level},}}\s)", stripped)
            for sub in subs:
                sub = sub.strip()
                if sub:
                    biz_parts.append(sub)
        elif sec_type == "unknown":
            # 按位置推断: 第一个 → global, 中间的 → api 或 biz
            # Position-based fallback: first → global, middle → api/biz
            if i <= 1:
                global_parts.append(stripped)
            elif outline and outline.get("api_groups"):
                subs = re.split(rf"\n(?=#{{{subsplit_level},}}\s)", stripped)
                for sub in subs:
                    sub = sub.strip()
                    if sub:
                        api_parts.append(sub)
            else:
                subs = re.split(rf"\n(?=#{{{subsplit_level},}}\s)", stripped)
                for sub in subs:
                    sub = sub.strip()
                    if sub:
                        biz_parts.append(sub)

    # 拼接 global 内容: 前导文本 + 明确标记为 global 的区块
    # Assemble global: preamble + explicitly classified global sections
    all_global = [global_preamble] + global_parts
    global_content = "\n\n".join(p for p in all_global if p.strip())

    # 映射 API groups / Map to outline API groups
    api_groups = outline.get("api_groups", []) if outline else []
    group_names = [g.get("group_name", "") for g in api_groups]
    for i, part in enumerate(api_parts):
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
    """从分块结构拼接纯 Markdown plan.md / Assemble clean plan.md from section structure.

    biz 类型 chunk 如有 mermaid 字段, 拼在 content 前面。
    For biz-type chunks, prepend mermaid content before plan text.
    """
    parts: List[str] = [sections.get("global", "")]
    in_biz = False
    for sec in sections.get("sections", []):
        sec_type = sec.get("type", "")
        content = sec.get("content", "")

        # 第一个 biz 类型前插入 section 标题 / Insert section heading before first biz
        if sec_type in ("biz", "biz_flow") and not in_biz:
            in_biz = True

        # biz chunk: Mermaid 在前, 计划文本在后 / Mermaid first, then plan text
        mermaid = sec.get("mermaid", "")
        if mermaid and mermaid.strip():
            if content.strip():
                content = mermaid.strip() + "\n\n" + content.strip()
            else:
                content = mermaid.strip()

        if content.strip():
            parts.append(content)
    return "\n\n".join(filter(None, parts))
