"""批注模式三阶段精准修订 / Three-phase chunked annotation revision.

Phase 1: 意图分析 (greedy-batched LLM → JSON)
Phase 2: 执行删除 (code only, zero LLM)
Phase 3: 内容生成 (per-chunk LLM with output window estimation)
"""

import json
import logging
from typing import Any, Dict, List

from agents.base import BaseAgent
from graph.state import GraphState
from i18n import get_language_name, _
from prompts.plan_reviser import (
    PLAN_ANNOTATION_ADD_SYSTEM,
    PLAN_ANNOTATION_ADD_USER,
    PLAN_ANNOTATION_INTENT_SYSTEM,
    PLAN_ANNOTATION_INTENT_USER,
    PLAN_ANNOTATION_UPDATE_SYSTEM,
    PLAN_ANNOTATION_UPDATE_USER,
)
from prompts.render import render_prompt

from . import helpers as _h
from .helpers import _
from .review import (
    _assemble_plan,
    _find_section_by_key,
    _load_or_parse_sections,
    _save_plan_sections,
)

logger = logging.getLogger(__name__)

# 合法的意图分析 action 值 / Valid intent analysis action values
_VALID_ACTIONS = {"delete", "update", "add", "noop"}


# ============================================================================
# 三阶段编排器 / Three-Phase Orchestrator
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

    # 定位: grep 批注 → 区块 / Map annotations to sections
    section_annotations = _map_annotations_to_sections(sections, annotations)

    if not section_annotations:
        logger.warning(_("review.no_sections_matched"))
        return plan_md

    # Phase 1: 意图分析 / Intent analysis
    token_counter = _get_token_counter(state)
    all_actions = _phase1_intent_analysis(
        sections, section_annotations, token_counter, state
    )

    # Phase 2: 执行删除 / Execute deletions
    _phase2_execute_deletions(sections, all_actions, annotations)

    # Phase 3: 内容生成 / Content generation
    _phase3_content_generation(
        sections, all_actions, annotations, token_counter, state, analysis, api_summary
    )

    # 拼接 / Re-assemble
    revised = _assemble_plan(sections)
    if memory_dir:
        _save_plan_sections(memory_dir, sections)
    return revised


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
