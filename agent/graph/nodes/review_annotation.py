"""批注模式三阶段精准修订 / Three-phase chunked annotation revision.

Phase 1: 意图分析 (greedy-batched LLM → JSON)
Phase 2: 执行删除 (code only, zero LLM)
Phase 3: 内容生成 (per-chunk LLM with output window estimation)
"""

import json
import logging
import re
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

    # 定位: 批注 → 区块 (selected_text + line_number) / Map annotations to sections
    section_annotations = _map_annotations_to_sections(sections, annotations, plan_md)

    if not section_annotations:
        logger.warning(_("review.no_sections_matched"))
        return plan_md

    # Phase 1: 意图分析 + 代码级绑定批注 / Intent analysis + bind annotations
    token_counter = _get_token_counter(state)
    all_actions = _phase1_intent_analysis(
        sections, section_annotations, token_counter, state
    )

    # Phase 2: 精确删除 / Precise deletions
    _phase2_execute_deletions(sections, all_actions, plan_md)

    # Phase 3: 块级内容生成 / Block-level content generation
    _phase3_content_generation(sections, all_actions, token_counter, state, plan_md)

    # 拼接 / Re-assemble
    revised = _assemble_plan(sections)
    if memory_dir:
        _save_plan_sections(memory_dir, sections)
    return revised


# ---------------------------------------------------------------------------
# Phase 1: 意图分析 / Intent Analysis
# ---------------------------------------------------------------------------


def _map_annotations_to_sections(
    sections: dict, annotations: List[dict], plan_md: str = "",
) -> Dict[str, List[dict]]:
    """将每条批注映射到其所属区块 / Map each annotation to its section.

    优先用 selected_text 子串匹配; 失败时用 line_number 落点兜底 (需 plan_md),
    避免批注被静默丢弃。Returns {section_key: [annotations]}.
    """
    mapping: Dict[str, List[dict]] = {}
    for ann in annotations:
        selected = ann.get("selected_text", "")
        # 1) selected_text 子串匹配 / substring match
        if selected:
            if selected in sections.get("global", ""):
                mapping.setdefault("__global__", []).append(ann)
                continue
            placed = False
            for sec in sections.get("sections", []):
                if selected in sec.get("content", ""):
                    mapping.setdefault(sec["key"], []).append(ann)
                    placed = True
                    break
            if placed:
                continue
        # 2) line_number 落点兜底 / line_number fallback
        if plan_md:
            key = _section_key_for_line(sections, plan_md, ann.get("line_number"))
            if key:
                mapping.setdefault(key, []).append(ann)
                continue
        logger.debug("Annotation not mapped to any section: %s", (selected or "")[:80])
    return mapping


def _section_key_for_line(sections: dict, plan_md: str, line_number) -> Any:
    """按 line_number 落点找所属区块 key / Find section key by line_number range."""
    if not isinstance(line_number, int):
        return None
    global_content = sections.get("global", "")
    g_base = _section_base_line(plan_md, global_content)
    if g_base is not None and global_content:
        if g_base <= line_number < g_base + global_content.count("\n") + 1:
            return "__global__"
    for sec in sections.get("sections", []):
        content = sec.get("content", "")
        base = _section_base_line(plan_md, content)
        if base is None:
            continue
        if base <= line_number < base + content.count("\n") + 1:
            return sec["key"]
    return None


# ---------------------------------------------------------------------------
# 动态定位辅助 / Dynamic block-location helpers (no hard-coded heading levels)
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"(?m)^(#{1,6})[ \t]+\S")


def _scan_headings(content: str) -> List[tuple]:
    """扫描所有 Markdown 标题 / Scan all markdown headings.

    Returns [(offset, level, line_text), ...] — 级别由 # 数量决定, 不写死。
    """
    headings = []
    for m in _HEADING_RE.finditer(content):
        offset = m.start()
        level = len(m.group(1))
        line_end = content.find("\n", offset)
        if line_end == -1:
            line_end = len(content)
        headings.append((offset, level, content[offset:line_end]))
    return headings


def _line_start_offset(text: str, line_number: int) -> int:
    """1-based 行号 → 字符偏移 (clamp) / 1-based line number to char offset."""
    lines = text.split("\n")
    line_number = max(1, min(line_number, len(lines)))
    return sum(len(lines[i]) + 1 for i in range(line_number - 1))


def _section_base_line(plan_md: str, content: str):
    """区块在整篇中的起始行 (1-based) / Section start line in plan_md, or None."""
    if not plan_md or not content:
        return None
    first_line = content.lstrip().split("\n", 1)[0]
    if not first_line:
        return None
    idx = plan_md.find(first_line)
    if idx == -1:
        return None
    return plan_md[:idx].count("\n") + 1


def _locate_anchor(content: str, annotation: dict, base_line) -> int:
    """定位批注锚点在 content 中的字符偏移 / Locate annotation anchor offset.

    优先 line_number (经 base_line 换算为本地行), 无效回退 selected_text。
    Returns -1 if not locatable.
    """
    selected = annotation.get("selected_text", "")
    line_number = annotation.get("line_number")
    if base_line is not None and isinstance(line_number, int):
        local_line = line_number - base_line + 1
        if local_line >= 1:
            off = max(0, min(_line_start_offset(content, local_line), len(content)))
            if selected:
                # 从锚点向后就近匹配, 消除重复文本歧义 / Nearest match at/after anchor
                near = content.find(selected, off)
                if near != -1 and near - off <= 2000:
                    return near
                # 锚点上方少量范围 / small window above anchor
                back = content.rfind(selected, max(0, off - 500), off + len(selected))
                if back != -1:
                    return back
            return off
    if selected:
        idx = content.find(selected)
        if idx != -1:
            return idx
    return -1


def _enclosing_block(content: str, anchor: int) -> tuple:
    """anchor 所在的动态标题块 span / Enclosing heading block span.

    取最近上方标题 (级别 L), 延伸到下一个级别 <= L 的标题为止。
    anchor 在首标题前则返回 (0, 首标题); 无标题则返回整块。
    """
    headings = _scan_headings(content)
    if not headings:
        return (0, len(content))
    cur_idx = -1
    for i, (off, _level, _text) in enumerate(headings):
        if off <= anchor:
            cur_idx = i
        else:
            break
    if cur_idx == -1:
        return (0, headings[0][0])
    start, level, _ = headings[cur_idx]
    end = len(content)
    for off, lvl, _text in headings[cur_idx + 1:]:
        if lvl <= level:
            end = off
            break
    return (start, end)


def _trunc(text: str, n: int = 80) -> str:
    """截断日志文本 / Truncate text for logs."""
    text = text.strip()
    return text[:n] + ("..." if len(text) > n else "")


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

    # 处理映射到 global 的批注 / Handle annotations mapped to global section
    if "__global__" in section_annotations:
        pending.insert(0, {
            "section": {
                "key": "__global__",
                "type": "global",
                "name": "Global",
                "content": sections.get("global", ""),
            },
            "annotations": section_annotations["__global__"],
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
                # 代码级绑定: 动作 ↔ 批注 (按 section 顺序) / Bind actions to annotations
                _bind_actions_to_annotations(actions, section_annotations)
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
                            "annotation": ann,
                        })
                break

            logger.warning(
                _("review.intent_validation_retry",
                  batch=batch_idx + 1, attempt=attempts,
                  errors="; ".join(errors))
            )

    return all_actions


def _bind_actions_to_annotations(
    actions: List[dict], section_annotations: Dict[str, List[dict]],
):
    """按 section 顺序把意图动作绑定到来源批注 / Bind actions to source annotations.

    现有 prompt 已保证「每条批注一个输出对象」, 故按 section_key 分组后
    与该 section 的批注列表按顺序配对; 数量不一致时按位置尽量兜底。
    """
    by_key: Dict[str, List[dict]] = {}
    for a in actions:
        by_key.setdefault(a.get("section_key", ""), []).append(a)
    for key, acts in by_key.items():
        anns = section_annotations.get(key, [])
        for i, act in enumerate(acts):
            if i < len(anns):
                act["annotation"] = anns[i]
            elif anns:
                act["annotation"] = anns[-1]
            else:
                act["annotation"] = None


# ---------------------------------------------------------------------------
# Phase 2: 代码删除 / Code Deletion
# ---------------------------------------------------------------------------


def _phase2_execute_deletions(
    sections: dict, actions: List[dict], plan_md: str = "",
):
    """执行所有 delete 动作 — 代码直接操作, 零 LLM。

    每个 delete 动作只处理其绑定的那条批注, 用 line_number + selected_text 精确定位:
    命中表格数据行则只删该行, 否则删除所在的动态标题块。
    """
    delete_actions = [a for a in actions if a.get("action") == "delete"]
    if not delete_actions:
        return

    deleted = 0
    for action in delete_actions:
        ann = action.get("annotation")
        if not ann:
            continue
        section_key = action.get("section_key", "")
        if section_key == "__global__":
            content = sections.get("global", "")
            base_line = _section_base_line(plan_md, content)
            new_content = _remove_annotation_target(content, ann, base_line)
            if new_content is not None:
                sections["global"] = new_content
                deleted += 1
            continue
        target = _find_section_by_key(sections, section_key)
        if target is None:
            continue
        base_line = _section_base_line(plan_md, target["content"])
        new_content = _remove_annotation_target(target["content"], ann, base_line)
        if new_content is not None:
            target["content"] = new_content
            deleted += 1

    if deleted > 0:
        logger.info(_("review.phase2_deleted", count=deleted))


def _remove_annotation_target(content: str, annotation: dict, base_line):
    """精确删除批注目标 / Precisely remove the annotation's target.

    优先删除命中的表格数据行, 否则删除所在的动态标题块。
    Returns modified content, or None if nothing was removed.
    """
    anchor = _locate_anchor(content, annotation, base_line)
    if anchor == -1:
        return None

    # 1) 表格数据行删除 / Table-row deletion
    row_result = _remove_table_rows(content, annotation, anchor)
    if row_result is not None:
        return row_result

    # 2) 动态标题块删除 / Dynamic heading-block deletion
    start, end = _enclosing_block(content, anchor)
    if start == 0 and end == len(content):
        # 无标题边界, 不安全整体删除 / No heading boundary — unsafe to delete
        return None
    removed = content[start:end]
    new_content = (content[:start].rstrip() + "\n\n" + content[end:].lstrip())
    new_content = re.sub(r"\n{3,}", "\n\n", new_content).strip()
    logger.info(_("review.delete_block", text=_trunc(removed)))
    return new_content


def _is_table_data_row(line: str) -> bool:
    """是否为表格数据行 (非分隔行) / Is a table data row (not a separator)."""
    s = line.strip()
    if not s.startswith("|"):
        return False
    # 排除 |---|:--:| 之类的分隔行 / Exclude separator rows
    return re.match(r"^\|[\s:|\-]+\|?\s*$", s) is None


def _remove_table_rows(content: str, annotation: dict, anchor: int):
    """若 selected_text 命中表格数据行, 仅删这些行 / Remove matched table rows only.

    Returns modified content, or None if this is not a table-row deletion.
    """
    selected = annotation.get("selected_text", "")
    if not selected:
        return None
    idx = content.find(selected, anchor)
    if idx == -1:
        idx = content.find(selected)
    if idx == -1:
        return None

    # 命中文本覆盖的整行范围 / Full-line span covered by the match
    seg_start = content.rfind("\n", 0, idx) + 1
    seg_end = content.find("\n", idx + len(selected))
    if seg_end == -1:
        seg_end = len(content)

    span_lines = [ln for ln in content[seg_start:seg_end].split("\n") if ln.strip()]
    if not span_lines or not all(_is_table_data_row(ln) for ln in span_lines):
        return None

    new_content = content[:seg_start].rstrip("\n") + "\n" + content[seg_end:].lstrip("\n")
    logger.info(_("review.delete_row", text=_trunc(selected)))
    return new_content.strip()


# ---------------------------------------------------------------------------
# Phase 3: 块级内容生成 (update / add) / Block-level Content Generation
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
    token_counter,
    state: GraphState,
    plan_md: str = "",
):
    """为 update/add 生成修订内容 — 块级精确 splice / Block-level revision.

    每个动作用 line_number + selected_text 定位其所属动态标题块,
    只把该块发给 LLM 并原地替换, 其余字节不动。
    """
    gen_actions = [
        a for a in actions
        if a.get("action") in ("update", "add") and a.get("annotation")
    ]
    if not gen_actions:
        return

    agent = _make_apply_agent(state)

    # 按 section 分组 / Group by section
    by_section: Dict[str, List[dict]] = {}
    for a in gen_actions:
        by_section.setdefault(a.get("section_key", ""), []).append(a)

    for section_key, acts in by_section.items():
        if section_key == "__global__":
            target = {"key": "__global__", "name": "Global",
                      "content": sections.get("global", "")}
        else:
            target = _find_section_by_key(sections, section_key)
        if target is None:
            continue

        base_line = _section_base_line(plan_md, target["content"])
        _apply_actions_to_section(target, acts, base_line, token_counter, agent)

        if section_key == "__global__":
            sections["global"] = target["content"]


def _apply_actions_to_section(
    target: dict, acts: List[dict], base_line, token_counter, agent: BaseAgent,
):
    """在单个 section 内按动态标题块逐块修订 / Revise per dynamic block within a section."""
    content = target["content"]
    section_name = target.get("name", target.get("key", "?"))

    # 定位每个动作所属块; 任一定位失败则回退整块处理 / Locate blocks; fallback whole section
    located = []
    for a in acts:
        anchor = _locate_anchor(content, a["annotation"], base_line)
        if anchor == -1:
            revised = _revise_block(
                content, [x["annotation"] for x in acts],
                "add" if any(x.get("action") == "add" for x in acts) else "update",
                section_name, token_counter, agent,
            )
            if revised and revised.strip():
                target["content"] = revised.strip()
            return
        start, end = _enclosing_block(content, anchor)
        located.append((start, end, a.get("action"), a["annotation"]))

    # 合并同一块的动作 / Merge actions sharing the same block span
    merged: Dict[tuple, dict] = {}
    for start, end, atype, ann in located:
        m = merged.setdefault((start, end), {"has_add": False, "anns": []})
        m["anns"].append(ann)
        if atype == "add":
            m["has_add"] = True

    # 按起点降序 splice, 避免前面的替换使后面偏移失效 / Splice bottom-up
    for (start, end) in sorted(merged, key=lambda s: s[0], reverse=True):
        info = merged[(start, end)]
        block_text = content[start:end]
        atype = "add" if info["has_add"] else "update"
        revised = _revise_block(
            block_text, info["anns"], atype, section_name, token_counter, agent,
        )
        if revised and revised.strip():
            content = (content[:start].rstrip() + "\n\n"
                       + revised.strip() + "\n\n" + content[end:].lstrip())
            content = re.sub(r"\n{3,}", "\n\n", content)
    target["content"] = content.strip()


def _revise_block(
    block_text: str, annotations: List[dict], action_type: str,
    section_name: str, token_counter, agent: BaseAgent,
):
    """把单个块 + 批注发给 LLM 生成修订块 / LLM-revise a single block.

    Returns the revised block text, or None if there is nothing to do.
    """
    if action_type == "add":
        system_prompt, user_template = PLAN_ANNOTATION_ADD_SYSTEM, PLAN_ANNOTATION_ADD_USER
    else:
        system_prompt, user_template = PLAN_ANNOTATION_UPDATE_SYSTEM, PLAN_ANNOTATION_UPDATE_USER

    annotations_text = _build_apply_user_prompt({"content": block_text}, annotations)
    if not annotations_text.strip():
        # 绑定已保证相关性, 无过滤兜底 / Binding guarantees relevance — unfiltered fallback
        annotations_text = _format_annotation_lines(annotations)
    if not annotations_text.strip():
        return None

    logger.info(
        _("review.phase3_block",
          name=section_name, type=action_type, tokens=token_counter.count(block_text))
    )
    system_rendered = render_prompt(system_prompt, language=get_language_name())
    prompt = render_prompt(
        user_template, section_content=block_text, annotations_list=annotations_text,
    )
    return agent.call_llm(prompt, system_rendered)


def _format_annotation_lines(annotations: List[dict]) -> str:
    """格式化批注列表为 prompt 文本 / Format annotations as prompt text."""
    lines = []
    for a in annotations:
        lines.append(
            f"- [Line ~{a.get('line_number', '?')}] "
            f'Selected: "{a.get("selected_text", "")}"\n'
            f'  Comment: "{a.get("review_comment", "")}"'
        )
    return "\n".join(lines)


def _build_apply_user_prompt(target: dict, annotations: List[dict]) -> str:
    """构建内容生成 USER prompt / Build content generation user prompt.

    从批注中提取 selected_text 和 review_comment，
    只保留 selected_text 出现在 content 中的批注。
    Filters annotations to those whose selected_text appears in the content.
    """
    content = target.get("content", "")
    matched = [
        a for a in annotations
        if a.get("selected_text", "") and a.get("selected_text", "") in content
    ]
    return _format_annotation_lines(matched)
