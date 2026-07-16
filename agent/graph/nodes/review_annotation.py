"""批注模式 Chunk 级精准修订 / Annotation-based chunk-level revision.

新设计（替代旧三阶段管线）/ New design (replaces old 3-phase pipeline):
  1. 批注 → chunk 映射 (代码级) / Map annotations to chunks (code-level)
  2. 意图分析 (LLM → noop/fix/delete_chunk/add_chunk) / Intent analysis (LLM)
  3. 执行 chunk 级操作 / Execute chunk-level actions
  4. _assemble_plan() 拼接 / Re-assemble plan
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

from agents.base import BaseAgent
from agents.plan_generator import PlanGenerator, _serialize_interfaces
from graph.state import GraphState
from i18n import get_language_name, _
from plugins.skill_loader import load_skill_extensions
from prompts.plan_generation import (
    PLAN_CHUNK_API_SECTION_SYSTEM,
    PLAN_CHUNK_API_SECTION_USER,
    PLAN_CHUNK_BIZ_SECTION_SYSTEM,
    PLAN_CHUNK_BIZ_SECTION_USER,
    PLAN_CHUNK_GLOBAL_SYSTEM,
    PLAN_CHUNK_GLOBAL_USER,
    PLAN_CHUNK_MERMAID_SYSTEM,
    PLAN_CHUNK_MERMAID_USER,
)
from prompts.plan_reviser import (
    PLAN_ANNOTATION_INTENT_SYSTEM,
    PLAN_ANNOTATION_INTENT_USER,
)
from prompts.render import render_prompt

from . import helpers as _h
from .helpers import _
from .review import (
    _assemble_plan,
    _find_section_by_key,
    _load_or_parse_sections,
    _save_plan_sections,
    _scan_headings,
)

logger = logging.getLogger(__name__)

# 合法的意图分析 action 值 / Valid intent analysis action values
_VALID_ACTIONS = {"noop", "fix", "delete_chunk", "add_chunk"}


# ============================================================================
# Chunk 级修订编排器 / Chunk-level Revision Orchestrator
# ============================================================================


def _annotation_chunked_revision(
    state: GraphState, plan_md: str, annotations_json: str,
    analysis: dict, api_summary: list,
) -> str:
    """Chunk 级精准批注修订 / Chunk-level annotation revision.

    1. 加载 chunk 注册表 + 批注 → chunk 映射
    2. LLM 意图分析: 每条批注 → {action: noop|fix|delete_chunk|add_chunk}
    3. 执行 chunk 级操作
    4. 保存并拼接
    """
    annotations = json.loads(annotations_json)
    memory_dir = state.get("memory_dir", "")
    outline = state.get("plan_outline")

    # 加载 skill 扩展 / Load skill extensions
    _skills_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'skills', 'builtin')
    _exts = load_skill_extensions('plan_generator', _h._settings, _skills_dir)

    # 加载 chunk 注册表 / Load chunk registry
    sections = _load_or_parse_sections(memory_dir, plan_md, outline)

    # 批注 → chunk 映射 / Map annotations to chunks
    section_annotations = _map_annotations_to_sections(sections, annotations, plan_md)
    if not section_annotations:
        logger.warning(_("review.no_sections_matched"))
        return plan_md

    # 意图分析 / Intent analysis (LLM)
    all_actions = _run_intent_analysis(sections, section_annotations, state)
    if not all_actions:
        return plan_md

    # 执行 chunk 级操作 / Execute chunk-level actions
    _execute_chunk_actions(sections, all_actions, state, analysis, api_summary,
                           skill_extensions=_exts, plan_md=plan_md)

    # 保存 + 拼接 / Save + assemble
    if memory_dir:
        _save_plan_sections(memory_dir, sections)
    return _assemble_plan(sections)


# ============================================================================
# 批注 → Chunk 映射 (保留自旧版) / Annotation → Chunk Mapping (kept)
# ============================================================================


def _map_annotations_to_sections(
    sections: dict, annotations: List[dict], plan_md: str = "",
) -> Dict[str, List[dict]]:
    """将每条批注映射到其所属 chunk / Map each annotation to its chunk.

    优先用 selected_text 子串匹配; 失败时用 line_number 兜底。
    Returns {section_key: [annotations]}.
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
    """按 line_number 落点找所属 chunk key / Find chunk key by line_number range."""
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


def _line_start_offset(text: str, line_number: int) -> int:
    """1-based 行号 → 字符偏移 / 1-based line number to char offset."""
    lines = text.split("\n")
    line_number = max(1, min(line_number, len(lines)))
    return sum(len(lines[i]) + 1 for i in range(line_number - 1))


def _section_base_line(plan_md: str, content: str):
    """Chunk 内容在整篇 plan_md 中的起始行 (1-based) / Section start line, or None."""
    if not plan_md or not content:
        return None
    first_line = content.lstrip().split("\n", 1)[0]
    if not first_line:
        return None
    idx = plan_md.find(first_line)
    if idx == -1:
        return None
    return plan_md[:idx].count("\n") + 1


# ============================================================================
# 意图分析 / Intent Analysis
# ============================================================================


def _run_intent_analysis(
    sections: dict,
    section_annotations: Dict[str, List[dict]],
    state: GraphState,
) -> List[dict]:
    """LLM 意图分析: 每条批注 → {section_key, action, reasoning} / Classify each annotation.

    使用全英文 prompt; JSON 输出必须包装为对象 {"actions": [...]}。
    Uses all-English prompt; JSON output must be an object (not bare array).
    """
    # 构建待分析列表 / Build pending list
    pending = []
    for sec in sections.get("sections", []):
        key = sec.get("key", "")
        if key in section_annotations:
            pending.append({
                "section": sec,
                "annotations": section_annotations[key],
            })
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
    from utils.token_counter import TokenCounter
    token_counter = TokenCounter(model=_h._settings.llm_model)

    system_rendered = render_prompt(PLAN_ANNOTATION_INTENT_SYSTEM)
    system_tokens = token_counter.count(system_rendered)
    output_reserve = _h._settings.llm_max_output_tokens
    max_batch_input = (
        _h._settings.llm_context_window
        - system_tokens
        - 200  # USER prompt skeleton
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

    agent = BaseAgent(
        api_key=_h._settings.llm_api_key,
        model=_h._settings.llm_model,
        temperature=0.1,
        max_retries=_h._settings.max_retries,
        max_steps=_h._settings.max_steps,
        base_url=_h._settings.llm_base_url,
        context_window=_h._settings.llm_context_window,
        max_output_tokens=_h._settings.llm_max_output_tokens,
        compression_threshold=_h._settings.llm_context_compression_threshold,
        rate_limit_delay=_h._settings.llm_rate_limit_delay,
        retry_base_delay=_h._settings.llm_retry_base_delay,
        max_concurrency=_h._settings.llm_max_concurrency,
        request_timeout=_h._settings.llm_request_timeout,
        extra_params=_h._settings.llm_extra_params,
    )

    for batch_idx, batch in enumerate(batches):
        prompt = _build_intent_user_prompt(batch)
        expected_count = sum(len(it["annotations"]) for it in batch)
        attempts = 0

        while attempts <= max_retries:
            agent.reset_steps()
            try:
                result = agent.call_llm_json(prompt, system_rendered)
                actions = result.get("actions", [])
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
            errors = _validate_intent_actions(actions, expected_count)
            if not errors:
                _bind_actions_to_batch(actions, batch)
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

    # 意图分布诊断 / Intent distribution diagnostics
    logger.info(_(
        "review.intent_distribution",
        total=len(all_actions),
        fix=sum(1 for a in all_actions if a.get("action") == "fix"),
        delete_chunk=sum(1 for a in all_actions if a.get("action") == "delete_chunk"),
        add=sum(1 for a in all_actions if a.get("action") == "add_chunk"),
        noop=sum(1 for a in all_actions if a.get("action") == "noop"),
    ))
    return all_actions


def _build_intent_user_prompt(batch: List[dict]) -> str:
    """构建意图分析 USER prompt / Build intent analysis user prompt."""
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
            f"### Section: {sec['key']} ({sec.get('type', '?')}, \"{sec.get('name', '?')}\")\n\n"
            f"{sec['content']}\n\n"
            f"Annotations for this section:\n"
            + "\n".join(ann_lines)
        )
    return "\n\n---\n\n".join(parts)


def _validate_intent_actions(actions: List[dict], expected_count: int = -1) -> List[str]:
    """校验 LLM 返回的意图分析结果 / Validate LLM intent analysis output."""
    errors = []
    if not isinstance(actions, list):
        return ["Expected JSON array in 'actions', got %s" % type(actions).__name__]
    if expected_count >= 0 and len(actions) != expected_count:
        errors.append(f"Expected {expected_count} action(s), got {len(actions)}")
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
        # add_chunk 必须有 section 字段 / add_chunk must specify section
        if action == "add_chunk" and not item.get("section"):
            errors.append(
                f"Item {i}: add_chunk requires 'section' field (single_api or biz_flows)"
            )
    return errors


def _bind_actions_to_batch(actions: List[dict], batch: List[dict]):
    """按批次内批注顺序绑定动作 / Bind actions to batch (section_key, annotation) positionally."""
    expected = [
        (item["section"]["key"], ann)
        for item in batch
        for ann in item["annotations"]
    ]
    for i, act in enumerate(actions):
        if i < len(expected):
            act["section_key"], act["annotation"] = expected[i]
        else:
            act["annotation"] = None


# ============================================================================
# Chunk 级操作执行器 / Chunk-level Action Executor
# ============================================================================


def _execute_chunk_actions(
    sections: dict,
    actions: List[dict],
    state: GraphState,
    analysis: dict,
    api_summary: list,
    plan_md: str = "",
    skill_extensions: List[str] | None = None,
):
    """执行 chunk 级操作 / Execute chunk-level actions.

    - noop → 跳过 / skip
    - fix → 重生成 chunk / regenerate chunk
    - delete_chunk → 从 outline + sections 移除 / remove from outline + sections
    - add_chunk → 更新 outline + 生成新 chunk / update outline + generate new chunk
    """
    outline = state.get("plan_outline", {})
    interfaces = state.get("interfaces", [])
    user_guidance = state.get("user_guidance", "")

    # 按 chunk_id 分组（一个 chunk 可能有多条批注） / Group by chunk_id
    by_chunk: Dict[str, List[dict]] = {}
    for a in actions:
        if a.get("action") == "noop":
            continue
        by_chunk.setdefault(a.get("section_key", ""), []).append(a)

    if not by_chunk:
        logger.info(_("review.noop_chunk"))
        return

    # 生成 agent / Create agent for chunk regeneration
    agent = PlanGenerator(_h._settings, _h._knowledge, skill_extensions=skill_extensions)
    iface_dicts = _serialize_interfaces(interfaces)
    iface_by_id = {d["test_id"]: d for d in iface_dicts if d.get("test_id")}

    for chunk_id, chunk_actions in by_chunk.items():
        # 合并该 chunk 的所有批注为一条 fix instruction / Consolidate annotations
        fix_text = _consolidate_annotations(
            [a["annotation"] for a in chunk_actions if a.get("annotation")]
        )

        action_types = {a.get("action") for a in chunk_actions}

        if "delete_chunk" in action_types:
            # 删除整个 chunk / Delete entire chunk
            _execute_delete_chunk(sections, outline, chunk_id)
            logger.info(_("review.deleted_chunk", key=chunk_id))
            continue

        if "add_chunk" in action_types:
            # 新增 chunk / Add new chunk
            add_action = next(a for a in chunk_actions if a.get("action") == "add_chunk")
            section_type = add_action.get("section", "")
            _execute_add_chunk(
                sections, outline, chunk_id, section_type, fix_text,
                agent, iface_by_id, analysis, api_summary, user_guidance, state,
            )
            continue

        if "fix" in action_types:
            # 重生成现有 chunk / Regenerate existing chunk
            if chunk_id == "__global__":
                _fix_global_chunk(sections, fix_text, outline, analysis, api_summary,
                                  agent, user_guidance)
                logger.info(_("review.fixed_global"))
                continue

            chunk = _find_section_by_key(sections, chunk_id)
            if not chunk:
                logger.warning(_("review.chunk_not_found", key=chunk_id))
                continue

            chunk_type = chunk.get("type", "")
            if chunk_type in ("api", "api_group"):
                group = _find_group_by_chunk_id(outline, chunk_id)
                if group:
                    _fix_api_chunk(chunk, group, fix_text, outline, analysis,
                                   api_summary, iface_by_id, agent, user_guidance)
                    logger.info(_("review.fixed_chunk", key=chunk_id))
            elif chunk_type in ("biz", "biz_flow"):
                flow = _find_flow_by_chunk_id(outline, chunk_id)
                if flow:
                    # 先重画 Mermaid / Regenerate Mermaid first
                    _regenerate_mermaid_for_flow(flow, iface_by_id, sections, agent)
                    # 再生成计划文本 / Then regenerate plan text
                    _fix_biz_chunk(chunk, flow, fix_text, outline, analysis,
                                   api_summary, iface_by_id, agent, user_guidance)
                    logger.info(_("review.fixed_chunk", key=chunk_id))

    # 保存更新后的 outline / Save updated outline
    memory_dir = state.get("memory_dir", "")
    if memory_dir:
        from graph.nodes.helpers import save_pipeline_artifact
        save_pipeline_artifact(memory_dir, "plan_outline.json", outline)


# ============================================================================
# Chunk 操作: fix / Fix Chunk Operations
# ============================================================================


def _fix_global_chunk(
    sections: dict, fix_text: str, outline: dict,
    analysis: dict, api_summary: list,
    agent: PlanGenerator, user_guidance: str,
):
    """重新生成 global (Business Understanding) chunk / Regenerate global chunk."""
    augmented = _augment_guidance(user_guidance, fix_text)
    outline_json = json.dumps(outline, ensure_ascii=False, indent=2)
    analysis_json = json.dumps(analysis, ensure_ascii=False, indent=2)
    api_summary_json = json.dumps(api_summary or [], ensure_ascii=False, indent=2)

    prompt = render_prompt(
        PLAN_CHUNK_GLOBAL_USER,
        outline=outline_json,
        requirement_analysis=analysis_json,
        api_summary=api_summary_json,
        user_guidance=augmented,
        reference_summary="(none)",
        language=get_language_name(),
    )
    system_msg = render_prompt(
        PLAN_CHUNK_GLOBAL_SYSTEM,
        outline=outline_json,
        language=get_language_name(),
    )
    agent.reset_steps()
    sections["global"] = agent.call_llm(prompt, system_msg)


def _fix_api_chunk(
    chunk: dict, group: dict, fix_text: str,
    outline: dict, analysis: dict, api_summary: list,
    iface_by_id: dict, agent: PlanGenerator, user_guidance: str,
):
    """重新生成 API group chunk / Regenerate API group chunk from outline."""
    augmented = _augment_guidance(user_guidance, fix_text)
    outline_json = json.dumps(outline, ensure_ascii=False, indent=2)
    global_context = sections_get_global_for_fix(analysis, api_summary)
    group_name = group.get("group_name", "")
    api_ids = group.get("api_ids", [])
    group_ifaces = [iface_by_id[aid] for aid in api_ids if aid in iface_by_id]

    prompt = render_prompt(
        PLAN_CHUNK_API_SECTION_USER,
        interface_defs=json.dumps(group_ifaces, ensure_ascii=False, indent=2),
        user_guidance=augmented,
        language=get_language_name(),
    )
    system_msg = render_prompt(
        PLAN_CHUNK_API_SECTION_SYSTEM,
        outline=outline_json,
        global_context=global_context,
        group_name=group_name,
        test_focus=group.get("test_focus", ""),
        group_api_ids=json.dumps(api_ids),
        language=get_language_name(),
    )
    agent.reset_steps()
    chunk["content"] = agent.call_llm(prompt, system_msg)


def _regenerate_mermaid_for_flow(
    flow: dict, iface_by_id: dict,
    sections: dict, agent: PlanGenerator,
):
    """重新绘制单个业务流的 Mermaid 图 / Re-draw Mermaid for a biz flow."""
    api_ids = flow.get("involved_apis", [])
    flow_ifaces = [iface_by_id[aid] for aid in api_ids if aid in iface_by_id]
    global_context = sections.get("global", "")

    prompt = render_prompt(
        PLAN_CHUNK_MERMAID_USER,
        flow_name=flow.get("name", ""),
        flow_description=flow.get("description", ""),
        interface_defs=json.dumps(flow_ifaces, ensure_ascii=False, indent=2),
    )
    system_msg = render_prompt(
        PLAN_CHUNK_MERMAID_SYSTEM,
        flow_name=flow.get("name", ""),
        flow_description=flow.get("description", ""),
        flow_api_ids=", ".join(api_ids),
        global_context=global_context,
        language=get_language_name(),
    )
    agent.reset_steps()
    mermaid_content = agent.call_llm(prompt, system_msg)

    # 找到对应的 chunk 并更新 mermaid 字段 / Find matching chunk and update mermaid
    chunk_id = flow.get("chunk_id", "")
    biz_key = f"biz_{chunk_id}"
    for sec in sections.get("sections", []):
        if sec.get("key") == biz_key or sec.get("chunk_id") == biz_key:
            sec["mermaid"] = mermaid_content
            break


def _fix_biz_chunk(
    chunk: dict, flow: dict, fix_text: str,
    outline: dict, analysis: dict, api_summary: list,
    iface_by_id: dict, agent: PlanGenerator, user_guidance: str,
):
    """重新生成 biz flow chunk（Mermaid 已重画）/ Regenerate biz flow chunk (Mermaid done)."""
    augmented = _augment_guidance(user_guidance, fix_text)
    outline_json = json.dumps(outline, ensure_ascii=False, indent=2)
    global_context = sections_get_global_for_fix(analysis, api_summary)
    api_ids = flow.get("involved_apis", [])
    flow_ifaces = [iface_by_id[aid] for aid in api_ids if aid in iface_by_id]

    flows_desc = [
        f"- Name: {flow.get('name', '?')}\n"
        f"  Description: {flow.get('description', '')}\n"
        f"  APIs: {', '.join(flow.get('involved_apis', []))}"
    ]
    flows_list = "\n\n".join(flows_desc)

    prompt = render_prompt(
        PLAN_CHUNK_BIZ_SECTION_USER,
        interface_defs=json.dumps(flow_ifaces, ensure_ascii=False, indent=2),
        user_guidance=augmented,
        language=get_language_name(),
    )
    system_msg = render_prompt(
        PLAN_CHUNK_BIZ_SECTION_SYSTEM,
        outline=outline_json,
        global_context=global_context,
        flows_list=flows_list,
        language=get_language_name(),
    )
    agent.reset_steps()
    chunk["content"] = agent.call_llm(prompt, system_msg)


# ============================================================================
# Chunk 操作: delete_chunk / add_chunk
# ============================================================================


def _execute_delete_chunk(sections: dict, outline: dict, chunk_id: str):
    """从 sections 和 outline 中移除 chunk / Remove chunk from sections and outline."""
    # 从 sections 中移除
    sections["sections"] = [
        s for s in sections.get("sections", [])
        if s.get("key") != chunk_id and s.get("chunk_id") != chunk_id
    ]
    # 从 outline 中移除
    if chunk_id.startswith("api_"):
        outline["api_groups"] = [
            g for g in outline.get("api_groups", [])
            if f"api_{g.get('chunk_id', '')}" != chunk_id
        ]
    elif chunk_id.startswith("biz_"):
        outline["biz_flows"] = [
            f for f in outline.get("biz_flows", [])
            if f"biz_{f.get('chunk_id', '')}" != chunk_id
        ]


def _execute_add_chunk(
    sections: dict, outline: dict, chunk_id: str,
    section_type: str, fix_text: str,
    agent: PlanGenerator, iface_by_id: dict,
    analysis: dict, api_summary: list,
    user_guidance: str, state: GraphState,
):
    """新增 chunk: 更新 outline + 生成内容 / Add chunk: update outline + generate content."""
    # 确定 section 类型 (代码级路由兜底) / Determine section type (code-level fallback)
    if section_type not in ("single_api", "biz_flows"):
        # 从 chunk_id 前缀推断 / Infer from chunk_id prefix
        section_type = "single_api" if chunk_id.startswith("api_") else "biz_flows"

    if section_type == "single_api":
        # 新增 API group
        new_group = {
            "chunk_id": chunk_id.replace("api_", ""),
            "group_name": chunk_id.replace("api_", "").replace("_", " ").title(),
            "api_ids": [],
            "test_focus": "",
        }
        outline.setdefault("api_groups", []).append(new_group)
        new_chunk = {
            "chunk_id": chunk_id,
            "key": chunk_id,
            "type": "api",
            "name": new_group["group_name"],
            "section": "single_api",
            "content": "",
        }
        sections.setdefault("sections", []).append(new_chunk)
        if fix_text:
            _fix_api_chunk(new_chunk, new_group, fix_text, outline,
                          analysis, api_summary, iface_by_id, agent, user_guidance)
    else:
        # 新增 biz flow
        new_flow = {
            "chunk_id": chunk_id.replace("biz_", ""),
            "name": chunk_id.replace("biz_", "").replace("_", " ").title(),
            "description": "",
            "involved_apis": [],
        }
        outline.setdefault("biz_flows", []).append(new_flow)
        new_chunk = {
            "chunk_id": chunk_id,
            "key": chunk_id,
            "type": "biz",
            "name": new_flow["name"],
            "section": "biz_flows",
            "content": "",
            "mermaid": "",
        }
        sections.setdefault("sections", []).append(new_chunk)
        if fix_text:
            _regenerate_mermaid_for_flow(new_flow, iface_by_id, sections, agent)
            _fix_biz_chunk(new_chunk, new_flow, fix_text, outline,
                          analysis, api_summary, iface_by_id, agent, user_guidance)


# ============================================================================
# 辅助函数 / Helpers
# ============================================================================


def _consolidate_annotations(annots: List[dict]) -> str:
    """合并多条批注为单个 fix instruction / Consolidate annotations into one instruction."""
    parts = []
    for a in annots:
        if not a:
            continue
        sel = a.get("selected_text", "")
        comment = a.get("review_comment", "")
        if comment:
            parts.append(f"- User comment: {comment}")
            if sel:
                parts.append(f"  Regarding: \"{sel}\"")
    return "\n".join(parts)


def _find_flow_by_chunk_id(outline: dict, chunk_id: str) -> Optional[dict]:
    """按 chunk_id 查找 biz flow / Find biz flow by chunk_id."""
    for f in outline.get("biz_flows", []):
        if f"biz_{f.get('chunk_id', '')}" == chunk_id:
            return f
    return None


def _find_group_by_chunk_id(outline: dict, chunk_id: str) -> Optional[dict]:
    """按 chunk_id 查找 API group / Find API group by chunk_id."""
    for g in outline.get("api_groups", []):
        if f"api_{g.get('chunk_id', '')}" == chunk_id:
            return g
    return None


def _augment_guidance(user_guidance: str, fix_text: str) -> str:
    """将修订批注追加到用户指导中 / Append revision instructions to user guidance."""
    base = user_guidance or "(none)"
    if not fix_text:
        return base
    return (
        f"{base}\n\n"
        f"## Revision Instructions (from User Feedback)\n"
        f"The user reviewed the previous plan and provided this feedback. "
        f"Apply ONLY the changes that are relevant to the content you are "
        f"generating. Keep everything else identical to the previous version."
        f"\n\n{fix_text}"
    )


def sections_get_global_for_fix(analysis: dict, api_summary: list) -> str:
    """获取 global context 用于 fix prompt（简化版）/ Get global context for fix prompts."""
    parts = []
    biz_summary = ""
    if isinstance(analysis, dict):
        biz_summary = analysis.get("business_summary", "")
    if biz_summary:
        parts.append(f"## Business Understanding\n{biz_summary}")
    if api_summary:
        parts.append(f"## API Summaries\n{json.dumps(api_summary, ensure_ascii=False, indent=2)}")
    return "\n\n".join(parts)
