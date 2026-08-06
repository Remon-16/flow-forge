"""批注模式 Chunk 级精准修订 / Annotation-based chunk-level revision.

新设计（替代旧三阶段管线）/ New design (replaces old 3-phase pipeline):
  1. 批注 → chunk 映射 (代码级) / Map annotations to chunks (code-level)
  2. 意图分析 (LLM → noop/fix/delete_chunk/add_chunk) / Intent analysis (LLM)
  3. 执行 chunk 级操作 / Execute chunk-level actions
  4. assemble_plan_md() 拼接 / Re-assemble plan
"""

import json
import logging
import os
from pathlib import Path
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
    _load_or_parse_sections,
    _save_plan_sections,
    _scan_headings,
)
from flow_forge_schemas.plan_sections import assemble_plan_md, find_section_by_key

logger = logging.getLogger(__name__)

# 合法的意图分析 action 值 / Valid intent analysis action values
_VALID_ACTIONS = {"noop", "fix", "delete_chunk", "add_chunk"}


# ============================================================================
# Chunk 级修订编排器 / Chunk-level Revision Orchestrator
# ============================================================================


def _annotation_chunked_revision(
    state: GraphState, annotations_json: str,
    analysis: dict, api_summary: list,
) -> str:
    """Chunk 级精准批注修订 / Chunk-level annotation revision.

    1. 加载 chunk 注册表 + 批注 → chunk 映射（优先 chunk_id）
    2. LLM 意图分析: 每条批注 → {action: noop|fix|delete_chunk|add_chunk}
    3. 执行 chunk 级操作
    4. 保存并拼接
    """
    annotations = json.loads(annotations_json)
    memory_dir = state.get("memory_dir", "")

    # 加载 skill 扩展 / Load skill extensions
    _skills_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'skills', 'builtin')
    _exts = load_skill_extensions('plan_generator', _h._settings, _skills_dir)

    # 加载 chunk 注册表 / Load chunk registry
    sections = _load_or_parse_sections(memory_dir)

    # 批注 → chunk 映射 (优先 chunk_id) / Map annotations to chunks (prefer chunk_id)
    section_annotations = _map_annotations_to_sections(sections, annotations)
    if not section_annotations:
        logger.warning(_("review.no_sections_matched"))
        return assemble_plan_md(sections)

    # 意图分析 / Intent analysis (LLM)
    all_actions = _run_intent_analysis(sections, section_annotations, state, skill_extensions=_exts)
    if not all_actions:
        return assemble_plan_md(sections)

    # 执行 chunk 级操作 / Execute chunk-level actions
    _execute_chunk_actions(sections, all_actions, state, analysis, api_summary,
                           skill_extensions=_exts)

    # 保存 + 拼接 / Save + assemble
    if memory_dir:
        _save_plan_sections(memory_dir, sections)
        # 修订后清除旧的 chunk 进度缓存，避免 resume 时使用过时进度
        # Delete stale chunk progress cache after revision to avoid outdated resume
        progress_path = Path(memory_dir) / "plan_chunks_progress.json"
        if progress_path.exists():
            progress_path.unlink()
            logger.debug("Deleted stale plan_chunks_progress.json after revision")
    return assemble_plan_md(sections)


# ============================================================================
# 批注 → Chunk 映射 / Annotation → Chunk Mapping
# ============================================================================


def _iter_all_sections(sections: dict):
    """遍历所有 section（business_understanding + single_api + biz_flows）。
    Iterate all sections including business_understanding, single_api, and biz_flows."""
    bu = sections.get("business_understanding")
    if isinstance(bu, dict):
        yield bu
    for sec in sections.get("single_api", []):
        yield sec
    for sec in sections.get("biz_flows", []):
        yield sec


def _map_annotations_to_sections(
    sections: dict, annotations: List[dict],
) -> Dict[str, List[dict]]:
    """将每条批注映射到其所属 chunk / Map each annotation to its chunk.

    优先用 chunk_id 直接匹配（find_section_by_key 现在支持所有 section 类型）。
    Priority: chunk_id direct match via find_section_by_key (now supports all section types).
    Returns {section_key: [annotations]}.
    """
    mapping: Dict[str, List[dict]] = {}
    for ann in annotations:
        # chunk_id 直接匹配 / chunk_id direct match (from Studio annotator DOM traversal)
        chunk_id = ann.get("chunk_id", "")
        if chunk_id:
            found = find_section_by_key(sections, chunk_id)
            if found:
                mapping.setdefault(found["key"], []).append(ann)
                continue
        # 无 chunk_id 则静默跳过（前端 findChunkId 返回 undefined 的情况）
        # No chunk_id: silently skip (when frontend findChunkId returns undefined)
        selected = ann.get("selected_text", "")
        logger.debug("Annotation not mapped to any section: %s", (selected or "")[:80])
    return mapping



# ============================================================================
# 意图分析 / Intent Analysis
# ============================================================================


def _run_intent_analysis(
    sections: dict,
    section_annotations: Dict[str, List[dict]],
    state: GraphState,
    skill_extensions: List[str] = None,
) -> List[dict]:
    """LLM 意图分析: 每条批注 → {section_key, action, reasoning} / Classify each annotation.

    使用全英文 prompt; JSON 输出必须包装为对象 {"actions": [...]}。
    Uses all-English prompt; JSON output must be an object (not bare array).
    """
    # 构建待分析列表 / Build pending list
    pending = []
    for sec in _iter_all_sections(sections):
        key = sec.get("key", "")
        if key in section_annotations:
            pending.append({
                "section": sec,
                "annotations": section_annotations[key],
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
        skill_extensions=skill_extensions,
    )

    for batch_idx, batch in enumerate(batches):
        prompt = _build_intent_user_prompt(batch)
        expected_count = sum(len(it["annotations"]) for it in batch)
        attempts = 0

        while attempts <= max_retries:
            agent.reset_steps()
            try:
                result = agent.call_llm_json_object(prompt, system_rendered, "actions")
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
# 所有操作只读写 plan_sections.json，不再依赖 outline
# All operations only read/write plan_sections.json; outline is no longer used
# ============================================================================


def _execute_chunk_actions(
    sections: dict,
    actions: List[dict],
    state: GraphState,
    analysis: dict,
    api_summary: list,
    skill_extensions: List[str] | None = None,
):
    """执行 chunk 级操作 / Execute chunk-level actions.

    - noop → 跳过 / skip
    - fix → 重生成 chunk / regenerate chunk
    - delete_chunk → 从 sections 移除 / remove from sections
    - add_chunk → 新增 chunk 到 sections / add new chunk to sections
    """
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
            _execute_delete_chunk(sections, chunk_id)
            logger.info(_("review.deleted_chunk", key=chunk_id))
            continue

        if "add_chunk" in action_types:
            # 新增 chunk / Add new chunk
            add_action = next(a for a in chunk_actions if a.get("action") == "add_chunk")
            section_type = add_action.get("section", "")
            _execute_add_chunk(
                sections, chunk_id, section_type, fix_text,
                agent, iface_by_id, analysis, api_summary, user_guidance,
            )
            continue

        if "fix" in action_types:
            # 重生成现有 chunk / Regenerate existing chunk
            chunk = find_section_by_key(sections, chunk_id)
            if not chunk:
                logger.warning(_("review.chunk_not_found", key=chunk_id))
                continue

            chunk_type = chunk.get("type", "")
            if chunk_type == "global":
                _fix_global_chunk(sections, chunk, fix_text, analysis, api_summary,
                                  agent, user_guidance)
                logger.info(_("review.fixed_global"))
            elif chunk_type == "api":
                _fix_api_chunk(chunk, fix_text, analysis,
                               api_summary, iface_by_id, agent, user_guidance)
                logger.info(_("review.fixed_chunk", key=chunk_id))
            elif chunk_type == "biz":
                # 先重画 Mermaid / Regenerate Mermaid first
                _regenerate_mermaid_for_flow(chunk, iface_by_id, sections, agent)
                # 再生成计划文本 / Then regenerate plan text
                _fix_biz_chunk(chunk, fix_text, analysis,
                               api_summary, iface_by_id, agent, user_guidance)
                logger.info(_("review.fixed_chunk", key=chunk_id))


# ============================================================================
# Chunk 操作: fix / Fix Chunk Operations
# ============================================================================


def _fix_global_chunk(
    sections: dict, chunk: dict, fix_text: str,
    analysis: dict, api_summary: list,
    agent: PlanGenerator, user_guidance: str,
):
    """重新生成 global (Business Understanding) chunk / Regenerate global chunk.

    与 _fix_api_chunk / _fix_biz_chunk 统一模式：接收 chunk dict，更新其 content。
    Unified pattern with _fix_api_chunk / _fix_biz_chunk: receives chunk dict, updates its content.
    """
    augmented = _augment_guidance(user_guidance, fix_text)
    analysis_json = json.dumps(analysis, ensure_ascii=False, indent=2)
    api_summary_json = json.dumps(api_summary or [], ensure_ascii=False, indent=2)

    prompt = render_prompt(
        PLAN_CHUNK_GLOBAL_USER,
        requirement_analysis=analysis_json,
        api_summary=api_summary_json,
        user_guidance=augmented,
        reference_summary="(none)",
        language=get_language_name(),
    )
    system_msg = render_prompt(
        PLAN_CHUNK_GLOBAL_SYSTEM,
        language=get_language_name(),
    )
    agent.reset_steps()
    chunk["content"] = agent.call_llm(prompt, system_msg)
    # 同步更新顶层 sections dict / Sync to top-level sections dict
    sections["business_understanding"] = chunk


def _fix_api_chunk(
    chunk: dict, fix_text: str,
    analysis: dict, api_summary: list,
    iface_by_id: dict, agent: PlanGenerator, user_guidance: str,
):
    """重新生成 API group chunk / Regenerate API group chunk from section data.

    不再依赖 outline group，所有数据直接从 chunk 自身获取。
    No longer depends on outline group; all data taken directly from chunk.
    """
    augmented = _augment_guidance(user_guidance, fix_text)
    global_context = sections_get_global_for_fix(analysis, api_summary)
    # 从 chunk 自身获取 / Get from chunk directly
    group_name = chunk.get("name", "")
    api_ids = chunk.get("api_ids", [])
    test_focus = chunk.get("test_focus", "")
    group_ifaces = [iface_by_id[aid] for aid in api_ids if aid in iface_by_id]

    prompt = render_prompt(
        PLAN_CHUNK_API_SECTION_USER,
        interface_defs=json.dumps(group_ifaces, ensure_ascii=False, indent=2),
        user_guidance=augmented,
        language=get_language_name(),
    )
    system_msg = render_prompt(
        PLAN_CHUNK_API_SECTION_SYSTEM,
        global_context=global_context,
        group_name=group_name,
        test_focus=test_focus,
        group_api_ids=json.dumps(api_ids),
        language=get_language_name(),
    )
    agent.reset_steps()
    chunk["content"] = agent.call_llm(prompt, system_msg)


def _regenerate_mermaid_for_flow(
    chunk: dict, iface_by_id: dict,
    sections: dict, agent: PlanGenerator,
):
    """重新绘制单个业务流的 Mermaid 图 / Re-draw Mermaid for a biz flow.

    只更新 chunk["mermaid"] 字段，不修改 chunk["content"]。
    Only updates chunk["mermaid"]; does NOT modify chunk["content"].
    所有数据从 chunk 自身获取（不再需要 outline flow 参数）。
    All data taken from chunk directly (no outline flow parameter needed).
    """
    api_ids = chunk.get("involved_apis", [])
    flow_ifaces = [iface_by_id[aid] for aid in api_ids if aid in iface_by_id]
    bu = sections.get("business_understanding", "")
    # 兼容新旧格式 / Compatible with old (str) and new (dict) format
    global_context = bu.get("content", "") if isinstance(bu, dict) else bu
    flow_name = chunk.get("name", "")
    flow_description = chunk.get("description", "")

    prompt = render_prompt(
        PLAN_CHUNK_MERMAID_USER,
        flow_name=flow_name,
        flow_description=flow_description,
        interface_defs=json.dumps(flow_ifaces, ensure_ascii=False, indent=2),
    )
    system_msg = render_prompt(
        PLAN_CHUNK_MERMAID_SYSTEM,
        flow_name=flow_name,
        flow_description=flow_description,
        flow_api_ids=", ".join(api_ids),
        global_context=global_context,
        language=get_language_name(),
    )
    agent.reset_steps()
    mermaid_content = agent.call_llm(prompt, system_msg)
    chunk["mermaid"] = mermaid_content


def _fix_biz_chunk(
    chunk: dict, fix_text: str,
    analysis: dict, api_summary: list,
    iface_by_id: dict, agent: PlanGenerator, user_guidance: str,
):
    """重新生成 biz flow chunk（Mermaid 已重画）/ Regenerate biz flow chunk (Mermaid done).

    所有数据从 chunk 自身获取（不再需要 outline flow 参数）。
    All data taken from chunk directly (no outline flow parameter needed).
    """
    augmented = _augment_guidance(user_guidance, fix_text)
    global_context = sections_get_global_for_fix(analysis, api_summary)
    # 从 chunk 自身获取 / Get from chunk directly
    api_ids = chunk.get("involved_apis", [])
    flow_ifaces = [iface_by_id[aid] for aid in api_ids if aid in iface_by_id]
    flow_name = chunk.get("name", "?")
    flow_description = chunk.get("description", "")
    involved_apis = chunk.get("involved_apis", [])

    flows_desc = [
        f"- Name: {flow_name}\n"
        f"  Description: {flow_description}\n"
        f"  APIs: {', '.join(involved_apis)}"
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
        global_context=global_context,
        flows_list=flows_list,
        language=get_language_name(),
    )
    agent.reset_steps()
    new_content = agent.call_llm(prompt, system_msg)
    # content 只存纯文本，mermaid 留在 chunk["mermaid"] 中
    # content stores plain text only; mermaid stays in chunk["mermaid"]
    # assemble_plan_md() 负责合并 / assemble_plan_md() handles merging
    chunk["content"] = new_content


# ============================================================================
# Chunk 操作: delete_chunk / add_chunk
# ============================================================================


def _execute_delete_chunk(sections: dict, chunk_id: str):
    """从 sections 中移除 chunk / Remove chunk from sections only.

    outline 不再维护 — plan_sections.json 是唯一数据源。
    outline is no longer maintained — plan_sections.json is the single source of truth.
    """
    for arr_name in ("single_api", "biz_flows"):
        arr = sections.get(arr_name, [])
        sections[arr_name] = [
            s for s in arr
            if s.get("key") != chunk_id and s.get("chunk_id") != chunk_id
        ]


def _execute_add_chunk(
    sections: dict, chunk_id: str,
    section_type: str, fix_text: str,
    agent: PlanGenerator, iface_by_id: dict,
    analysis: dict, api_summary: list,
    user_guidance: str,
):
    """新增 chunk 到 sections / Add new chunk to sections.

    outline 不再维护 — plan_sections.json 是唯一数据源。
    outline is no longer maintained — plan_sections.json is the single source of truth.

    若 chunk_id 已存在则自动追加后缀去重 / Auto-append suffix if chunk_id already exists.
    """
    # chunk_id 去重 / Dedup: avoid overwriting existing chunks
    original = chunk_id
    suffix = 1
    while find_section_by_key(sections, chunk_id):
        suffix += 1
        chunk_id = f"{original}_{suffix}"
    if chunk_id != original:
        logger.info(_("review.chunk_id_dedup", original=original, assigned=chunk_id))

    # 确定 section 类型 (代码级路由兜底) / Determine section type (code-level fallback)
    if section_type not in ("single_api", "biz_flows"):
        section_type = "single_api" if chunk_id.startswith("api_") else "biz_flows"

    if section_type == "single_api":
        new_chunk = {
            "chunk_id": chunk_id,
            "key": chunk_id,
            "type": "api",
            "name": chunk_id.replace("api_", "").replace("_", " ").title(),
            "section": "single_api",
            "content": "",
            "api_ids": [],
            "test_focus": "",
        }
        sections.setdefault("single_api", []).append(new_chunk)
        if fix_text:
            _fix_api_chunk(new_chunk, fix_text, analysis,
                          api_summary, iface_by_id, agent, user_guidance)
    else:
        new_chunk = {
            "chunk_id": chunk_id,
            "key": chunk_id,
            "type": "biz",
            "name": chunk_id.replace("biz_", "").replace("_", " ").title(),
            "section": "biz_flows",
            "content": "",
            "mermaid": "",
            "involved_apis": [],
            "description": "",
        }
        sections.setdefault("biz_flows", []).append(new_chunk)
        if fix_text:
            _regenerate_mermaid_for_flow(new_chunk, iface_by_id, sections, agent)
            _fix_biz_chunk(new_chunk, fix_text, analysis,
                          api_summary, iface_by_id, agent, user_guidance)


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
    """获取 global context 用于 fix prompt（简化版）/ Get global context for fix prompts.

    从 section 对象的 content 字段读取（兼容新旧格式）。
    Reads from section object's content field (compatible with old and new formats).
    """
    parts = []
    biz_summary = ""
    if isinstance(analysis, dict):
        biz_summary = analysis.get("business_summary", "")
    if biz_summary:
        parts.append(f"## Business Understanding\n{biz_summary}")
    if api_summary:
        parts.append(f"## API Summaries\n{json.dumps(api_summary, ensure_ascii=False, indent=2)}")
    return "\n\n".join(parts)
