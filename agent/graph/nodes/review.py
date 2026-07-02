"""审核节点 — 人工确认和计划修订。

Review nodes: human confirmation interrupt and plan revision.
Supports two revision modes:
  - Annotation mode ("r"): 3-phase chunked precise revision
  - Text mode ("n"): direct PLAN_REVISER call (with impact-analysis fallback)
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from agents.base import BaseAgent
from agents.plan_generator import PlanGenerator, _serialize_interfaces
from graph.state import GraphState
from i18n import get_language_name, _
from prompts.plan_reviser import (
    PLAN_ANNOTATION_ADD_SYSTEM,
    PLAN_ANNOTATION_ADD_USER,
    PLAN_ANNOTATION_INTENT_SYSTEM,
    PLAN_ANNOTATION_INTENT_USER,
    PLAN_ANNOTATION_UPDATE_SYSTEM,
    PLAN_ANNOTATION_UPDATE_USER,
    PLAN_REVISION_ANALYSIS_SYSTEM,
    PLAN_REVISION_ANALYSIS_USER,
    PLAN_REVISER_SYSTEM,
    PLAN_REVISER_USER,
)
from prompts.render import render_prompt

from . import helpers as _h
from .helpers import _, _step, _sl, save_pipeline_artifact, save_pipeline_state

logger = logging.getLogger(__name__)

# 合法的意图分析 action 值 / Valid intent analysis action values
_VALID_ACTIONS = {"delete", "update", "add", "noop"}


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
# 三阶段分块精准修订 (批注模式) / Three-Phase Chunked Annotation Revision
# ============================================================================


def _annotation_chunked_revision(
    state: GraphState, plan_md: str, annotations_json: str,
    analysis: dict, api_summary: list,
) -> str:
    """三阶段分块精准修订 / Three-phase chunked annotation revision.

    Phase 1: grep map + intent analysis (batched LLM, JSON output)
    Phase 2: execute deletions (code only, zero LLM)
    Phase 3: content generation for update/add (per-chunk LLM with output estimation)
    """
    annotations = json.loads(annotations_json)
    memory_dir = state.get("memory_dir", "")

    # 加载分块结构 / Load section structure
    sections = _load_or_parse_sections(memory_dir, plan_md, state.get("plan_outline"))

    # ---- 定位: grep 批注 → 区块 / Map annotations to sections ----
    section_annotations = _map_annotations_to_sections(sections, annotations)

    if not section_annotations:
        logger.warning(_("review.no_sections_matched"))
        return plan_md

    matched_count = sum(len(v) for v in section_annotations.values())
    logger.info(
        _("review.annotation_chunked",
          matched=matched_count, sections=len(section_annotations))
    )

    # ---- Phase 1: 意图分析 / Intent analysis ----
    token_counter = _get_token_counter(state)
    all_actions = _phase1_intent_analysis(
        sections, section_annotations, token_counter, state
    )

    if not all_actions:
        logger.warning("Phase 1 produced no actions, returning original plan")
        return plan_md

    # ---- Phase 2: 执行删除 / Execute deletions ----
    _phase2_execute_deletions(sections, all_actions, annotations)

    # ---- Phase 3: 内容生成 / Content generation ----
    _phase3_content_generation(
        sections, all_actions, annotations, token_counter, state, analysis, api_summary
    )

    # ---- 拼接 + 保存 / Re-assemble + save ----
    revised = _assemble_plan(sections)
    if memory_dir:
        _save_plan_sections(memory_dir, sections)
    return revised


# ---------------------------------------------------------------------------
# Section loading / parsing / 分块加载与解析
# ---------------------------------------------------------------------------


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

    复用与 _targeted_regenerate 相同的 ## 分割逻辑。
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


# ---------------------------------------------------------------------------
# Phase 1: 意图分析 / Intent Analysis
# ---------------------------------------------------------------------------


def _map_annotations_to_sections(
    sections: dict, annotations: List[dict],
) -> Dict[str, List[dict]]:
    """grep: 将每条批注映射到包含其 selected_text 的区块。

    Map each annotation to the section containing its selected_text.
    Returns {section_key: [annotations]}.
    """
    mapping: Dict[str, List[dict]] = {}
    for ann in annotations:
        selected = ann.get("selected_text", "")
        if not selected:
            continue
        # 搜索 global / Search global
        if selected in sections.get("global", ""):
            mapping.setdefault("__global__", []).append(ann)
            continue
        # 搜索 sections / Search sections
        found = False
        for sec in sections.get("sections", []):
            if selected in sec.get("content", ""):
                mapping.setdefault(sec["key"], []).append(ann)
                found = True
                break
        if not found:
            logger.debug("Annotation selected_text not found in any section: %s", selected[:80])
    return mapping


def _validate_intent_actions(actions: List[dict]) -> List[str]:
    """校验 LLM 返回的意图分析结果 / Validate LLM intent analysis output.

    Returns a list of error messages (empty = valid).
    """
    errors = []
    if not isinstance(actions, list):
        return ["Expected JSON array, got %s" % type(actions).__name__]
    for i, item in enumerate(actions):
        if not isinstance(item, dict):
            errors.append(f"Item {i}: expected object, got {type(item).__name__}")
            continue
        action = item.get("action", "")
        if action not in _VALID_ACTIONS:
            errors.append(
                f"Item {i}: invalid action '{action}', must be one of {_VALID_ACTIONS}"
            )
        if not item.get("section_key"):
            errors.append(f"Item {i}: missing section_key")
    return errors


def _get_token_counter(state: GraphState):
    """获取 TokenCounter 实例 / Get TokenCounter for estimation."""
    from utils.token_counter import TokenCounter
    return TokenCounter(model=_h._settings.llm_model)


def _make_intent_agent(state: GraphState) -> BaseAgent:
    """创建意图分析用的 LLM agent (温度极低) / Agent for intent analysis (very low temp)."""
    return BaseAgent(
        api_key=_h._settings.llm_api_key,
        model=_h._settings.llm_model,
        temperature=0.1,
        max_tokens=512,  # JSON 输出很小 / JSON output is tiny
        base_url=_h._settings.llm_base_url,
        max_steps=_h._settings.max_steps,
        context_window=_h._settings.llm_context_window,
    )


def _make_apply_agent(state: GraphState) -> BaseAgent:
    """创建内容生成用的 LLM agent / Agent for content generation."""
    return BaseAgent(
        api_key=_h._settings.llm_api_key,
        model=_h._settings.llm_model,
        temperature=0.3,
        max_tokens=_h._settings.llm_max_output_tokens,
        base_url=_h._settings.llm_base_url,
        max_steps=_h._settings.max_steps,
        context_window=_h._settings.llm_context_window,
    )


def _build_intent_user_prompt(batch: List[dict]) -> str:
    """构建意图分析 USER prompt / Build intent analysis user prompt.

    batch: [{section, annotations}, ...]
    """
    parts = []
    for item in batch:
        sec = item["section"]
        anns = item["annotations"]
        ann_lines = []
        for a in anns:
            ann_lines.append(
                f"- [Line ~{a.get('line_number', '?')}] "
                f'Selected: "{a.get("selected_text", "")}"\n'
                f'  Comment: "{a.get("review_comment", "")}"'
            )
        parts.append(
            f"### Section: {sec['key']} ({sec['type']}, \"{sec['name']}\")\n\n"
            f"{sec['content']}\n\n"
            f"Annotations for this section:\n"
            + "\n".join(ann_lines)
        )
    return "\n\n---\n\n".join(parts)


def _phase1_intent_analysis(
    sections: dict,
    section_annotations: Dict[str, List[dict]],
    token_counter,
    state: GraphState,
) -> List[dict]:
    """贪心分批意图分析 + 校验重试 / Greedy-batched intent analysis with validation.

    不断加区块到当前批次, 直到 token 预算用尽, 然后起新批次。
    每个批次独立重置步数计数器, 拥有完整的 max_retries 预算。
    """
    # 构建待处理列表 / Build pending list
    pending = []
    for sec in sections.get("sections", []):
        key = sec.get("key", "")
        if key in section_annotations:
            pending.append({
                "section": sec,
                "annotations": section_annotations[key],
            })

    if not pending:
        return []

    # 贪心分批 / Greedy batching
    # 渲染 system prompt 以计算准确 token 数 / Render system prompt for accurate token count
    system_rendered = render_prompt(
        PLAN_ANNOTATION_INTENT_SYSTEM,
        language=get_language_name(),
    )
    system_tokens = token_counter.count(system_rendered)
    user_skeleton_tokens = 200  # USER prompt 骨架 (不含 section content)
    output_reserve = 512       # JSON 输出极小
    max_batch_input = (
        _h._settings.llm_context_window
        - system_tokens
        - user_skeleton_tokens
        - output_reserve
    )

    batches = []
    current_batch = []
    current_tokens = 0
    for item in pending:
        item_tokens = (
            token_counter.count(item["section"]["content"])
            + token_counter.count(json.dumps(item["annotations"], ensure_ascii=False))
        )
        if current_batch and current_tokens + item_tokens > max_batch_input:
            batches.append(current_batch)
            current_batch = []
            current_tokens = 0
        current_batch.append(item)
        current_tokens += item_tokens
    if current_batch:
        batches.append(current_batch)

    logger.info(
        _("review.phase1_batching",
          batches=len(batches),
          total=sum(len(b["annotations"]) for b in pending))
    )

    # 逐批调用 LLM + 校验重试 / Call LLM per batch with validation + retry
    all_actions = []
    max_retries = _h._settings.max_retries
    agent = _make_intent_agent(state)

    for batch_idx, batch in enumerate(batches):
        prompt = _build_intent_user_prompt(batch)
        attempts = 0

        while attempts <= max_retries:
            # 每个批次独立重置步数 / Reset steps for each batch
            agent.reset_steps()

            try:
                actions = agent.call_llm_json(prompt, system_rendered)
            except Exception as e:
                attempts += 1
                if attempts > max_retries:
                    raise
                logger.warning(
                    _("review.intent_llm_error",
                      batch=batch_idx + 1, attempt=attempts, error=str(e))
                )
                continue

            # 校验 / Validate
            errors = _validate_intent_actions(actions)
            if not errors:
                all_actions.extend(actions)
                logger.info(
                    _("review.intent_batch_ok",
                      batch=batch_idx + 1, actions=len(actions))
                )
                break

            attempts += 1
            if attempts > max_retries:
                logger.error(
                    _("review.intent_validation_exhausted",
                      batch=batch_idx + 1, errors="; ".join(errors))
                )
                # 重试耗尽, 标记为 noop / Exhausted, mark all as noop
                for item in batch:
                    for ann in item["annotations"]:
                        all_actions.append({
                            "section_key": item["section"]["key"],
                            "action": "noop",
                            "reasoning": "Validation retry exhausted",
                        })
                break

            logger.warning(
                _("review.intent_validation_retry",
                  batch=batch_idx + 1, attempt=attempts,
                  errors="; ".join(errors))
            )

    return all_actions


# ---------------------------------------------------------------------------
# Phase 2: 代码删除 / Code Deletion
# ---------------------------------------------------------------------------


def _phase2_execute_deletions(
    sections: dict, actions: List[dict], annotations: List[dict],
):
    """执行所有 delete 动作 — 代码直接操作, 零 LLM。

    Execute all delete actions in code (zero LLM calls).
    Removes the subsection containing the annotated selected_text.
    """
    delete_actions = [a for a in actions if a.get("action") == "delete"]
    if not delete_actions:
        return

    deleted = 0
    for action in delete_actions:
        section_key = action.get("section_key", "")
        target = _find_section_by_key(sections, section_key)
        if target is None:
            continue

        # 用关联批注的 selected_text 定位 / Use annotation's selected_text as anchor
        if _remove_text_block(target, annotations):
            deleted += 1

    if deleted > 0:
        logger.info(_("review.phase2_deleted", count=deleted))


def _remove_text_block(target: dict, annotations: List[dict]) -> bool:
    """从区块 content 中移除 selected_text 所在的子区块。

    向前查找最近的 \\n#### 或 \\n### 标题,
    向后查找下一个同级或上级标题, 整体移除。

    Remove the subsection containing selected_text.
    Returns True if a block was removed.
    """
    content = target["content"]

    # 找到第一个在 content 中匹配的 selected_text / Find first matching annotation
    matched_selected = ""
    for ann in annotations:
        sel = ann.get("selected_text", "")
        if sel and sel in content:
            matched_selected = sel
            break
    if not matched_selected:
        return False

    idx = content.find(matched_selected)
    if idx == -1:
        return False

    # 向前找子区块起始 / Find subsection start (nearest #### or ### heading)
    block_start = content.rfind("\n#### ", 0, idx)
    if block_start == -1:
        block_start = content.rfind("\n### ", 0, idx)
    if block_start == -1:
        return False  # 找不到边界, 不安全删除

    # 确定标题层级 / Determine heading level
    after_start = content[block_start + 1:]  # skip leading \n
    if after_start.startswith("#### "):
        heading_level = "#### "
    else:
        heading_level = "### "

    # 向后找子区块结束 / Find subsection end (next same-level or higher heading)
    next_block = content.find(f"\n{heading_level}", idx + len(matched_selected))
    if next_block == -1:
        next_block = content.find("\n### ", idx + len(matched_selected))
        if next_block == -1:
            next_block = content.find("\n## ", idx + len(matched_selected))
    if next_block == -1:
        next_block = len(content)

    # 移除 / Remove
    removed_text = content[block_start:next_block].strip()
    target["content"] = (
        content[:block_start].rstrip() + "\n\n" + content[next_block:].lstrip()
    )
    target["content"] = target["content"].replace("\n\n\n", "\n\n").strip()

    logger.info(
        _("review.delete_block",
          text=removed_text[:80] + ("..." if len(removed_text) > 80 else ""))
    )
    return True


# ---------------------------------------------------------------------------
# Phase 3: 内容生成 (update / add) / Content Generation
# ---------------------------------------------------------------------------


def _phase3_content_generation(
    sections: dict,
    actions: List[dict],
    annotations: List[dict],
    token_counter,
    state: GraphState,
    analysis: dict,
    api_summary: list,
):
    """为 update/add 的区块生成修订内容 / Generate revised content for update/add.

    按区块单独调用 LLM, update 和 add 使用不同的 prompt。
    预估输出 tokens, 超过 max_output_tokens 时拆分为逐条处理。
    """
    # 筛选需要内容生成的 / Filter actions needing content generation
    chunk_actions: Dict[str, List[dict]] = {}
    for action in actions:
        if action.get("action") in ("update", "add"):
            key = action.get("section_key", "")
            chunk_actions.setdefault(key, []).append(action)

    if not chunk_actions:
        return

    max_output = _h._settings.llm_max_output_tokens
    agent = _make_apply_agent(state)

    for section_key, acts in chunk_actions.items():
        target = _find_section_by_key(sections, section_key)
        if target is None:
            continue

        # 按 action 类型分组 / Group by action type
        updates = [a for a in acts if a.get("action") == "update"]
        adds = [a for a in acts if a.get("action") == "add"]

        # 处理 update / Apply updates
        if updates:
            _apply_content_batch(
                target, updates, annotations, token_counter, max_output, agent,
                PLAN_ANNOTATION_UPDATE_SYSTEM, PLAN_ANNOTATION_UPDATE_USER,
                "update", state,
            )

        # 处理 add / Apply adds
        if adds:
            _apply_content_batch(
                target, adds, annotations, token_counter, max_output, agent,
                PLAN_ANNOTATION_ADD_SYSTEM, PLAN_ANNOTATION_ADD_USER,
                "add", state,
            )


def _estimate_apply_output(
    target: dict, actions: List[dict], token_counter,
) -> int:
    """预估 update/add 后的输出 token 数 / Estimate output tokens after applying actions.

    update: 输出 ≈ 输入 × 1.2 (修改不改变量级)
    add: 输出 ≈ 输入 + add_count × avg_subsection × 1.5
    """
    content = target["content"]
    input_tokens = token_counter.count(content)

    add_count = sum(1 for a in actions if a.get("action") == "add")

    if add_count == 0:
        return int(input_tokens * 1.2)

    # 计算子节平均大小 / Average subsection size
    subsections = [s for s in content.split("\n#### ") if s.strip()]
    num_subsections = max(len(subsections), 1)
    avg_tokens = input_tokens / num_subsections

    add_contribution = add_count * avg_tokens * 1.5
    return int(input_tokens + add_contribution)


def _build_apply_user_prompt(target: dict, actions: List[dict]) -> str:
    """构建内容生成 USER prompt / Build content generation user prompt.

    Formats annotations as a readable list for the apply prompt.
    """
    ann_lines = []
    for a in actions:
        ann_lines.append(
            f"- [Line ~{a.get('line_number', '?')}] "
            f'Selected: "{a.get("selected_text", "")}"\n'
            f'  Comment: "{a.get("review_comment", "")}"'
        )
    return "\n".join(ann_lines)


def _apply_content_batch(
    target: dict,
    actions: List[dict],
    annotations: List[dict],
    token_counter,
    max_output: int,
    agent: BaseAgent,
    system_prompt: str,
    user_prompt_template: str,
    action_type: str,
    state: GraphState,
):
    """单类型内容生成 — 输出窗口预估 + 拆分。

    Single-type content generation with output estimation and splitting.
    Uses the provided system_prompt (update or add variant).
    """
    estimated_output = _estimate_apply_output(target, actions, token_counter)
    input_tokens = token_counter.count(target["content"])
    section_name = target.get("name", target.get("key", "?"))

    if estimated_output < max_output and input_tokens < _h._settings.llm_context_window - 4096:
        # 单次调用 / Single call
        logger.info(
            _("review.phase3_generating",
              name=section_name, type=action_type, estimated=estimated_output)
        )
        # 渲染 system prompt / Render system prompt
        system_rendered = render_prompt(system_prompt, language=get_language_name())
        annotations_text = _build_apply_user_prompt(target, actions)
        prompt = render_prompt(
            user_prompt_template,
            section_content=target["content"],
            annotations_list=annotations_text,
        )
        response = agent.call_llm(prompt, system_rendered)
        if response.strip():
            target["content"] = response.strip()
    else:
        # 逐条处理 / Process one annotation at a time
        logger.info(
            _("review.phase3_split",
              name=section_name, estimated=estimated_output, max=max_output)
        )
        system_rendered = render_prompt(system_prompt, language=get_language_name())
        for act in actions:
            annotations_text = _build_apply_user_prompt(target, [act])
            prompt = render_prompt(
                user_prompt_template,
                section_content=target["content"],
                annotations_list=annotations_text,
            )
            response = agent.call_llm(prompt, system_rendered)
            if response.strip():
                target["content"] = response.strip()


# ============================================================================
# 回退路径: 影响分析 + 分块重生成 / Fallback: Impact Analysis + Chunked Regeneration
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

    # 渲染 {{outline}} 占位符 (Root Cause 4a fix)
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
# 精准分块重生成 / Targeted Chunck Regeneration (used by fallback path)
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
    Fix: flows_list parameter mismatch in Phase C (Root Cause 2).
    新增: 通过 augmented_guidance 注入修订反馈 (Root Cause 1 fix).
    """
    agent = PlanGenerator(_h._settings, _h._knowledge)
    interfaces = state.get("interfaces", [])
    user_guidance = state.get("user_guidance", "")
    augmented_guidance = _augment_guidance(user_guidance, feedback, feedback_type)
    iface_dicts = _serialize_interfaces(interfaces)
    iface_by_id = {d["test_id"]: d for d in iface_dicts if d.get("test_id")}

    # 解析现有 plan.md 为 sections / Split existing plan.md by ## headers
    sections_list = re.split(r"\n(?=##\s)", plan_md)

    # 保留全局 section / Keep global sections
    global_sections = []
    api_sections_map = {}
    biz_sections_map = {}
    for sec in sections_list:
        if sec.startswith("## 1.") or sec.startswith("## 4.") or "Business Understanding" in sec[:80] or "Flowchart" in sec[:80] or "Mermaid" in sec[:80]:
            global_sections.append(sec)
        elif sec.startswith("## 2.") or "Single Interface" in sec[:80]:
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

    # Regenerate global context / always regenerated to provide updated context
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
    global_context = agent.call_llm(global_prompt, PLAN_CHUNK_GLOBAL_SYSTEM)

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

        # Fix (Root Cause 2): 构造 flows_list 字符串, 匹配模板的 {{flows_list}} 占位符
        # Build flows_list string matching the {{flows_list}} placeholder in the template
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
