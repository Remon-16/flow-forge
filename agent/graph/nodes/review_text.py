"""n 模式文本反馈修订 — 统一走 Chunk 级操作 / Text feedback revision via chunk-level ops.

新设计（与 r 模式共享 chunk 操作代码）/ New design (shares chunk ops with r mode):
  Step 1: Section 影响分析 (1 LLM → 哪些 section 受影响)
  Step 2: 逐 section Chunk 意图分析 (LLM → noop/fix/delete_chunk/add_chunk)
  Step 3: 执行 chunk 级操作 (共用 review_annotation._execute_chunk_actions)
"""

import json
import logging
import os
from typing import Dict, List, Optional

from agents.base import BaseAgent
from graph.state import GraphState
from i18n import get_language_name, _
from plugins.skill_loader import load_skill_extensions
from prompts.plan_reviser import (
    PLAN_SECTION_IMPACT_SYSTEM,
    PLAN_SECTION_IMPACT_USER,
    PLAN_TEXT_CHUNK_INTENT_SYSTEM,
    PLAN_TEXT_CHUNK_INTENT_USER,
)
from prompts.render import render_prompt

from . import helpers as _h
from .helpers import _
from .review import (
    _assemble_plan,
    _load_or_parse_sections,
    _save_plan_sections,
)
from .review_annotation import _execute_chunk_actions

logger = logging.getLogger(__name__)


# ============================================================================
# n 模式入口 / Text Revision Entry Point
# ============================================================================


def _text_revision(
    state: GraphState, plan_md: str, feedback: str,
    analysis: dict, api_summary: list,
) -> str:
    """文本反馈修订 — Section 分析 → Chunk 意图 → 执行 / Text revision via chunk-level ops.

    Step 1: 确定受影响 section / Determine affected sections
    Step 2: 逐 section 做 chunk 意图分析 / Per-section chunk intent analysis
    Step 3: 执行 chunk 操作 (与 r 模式共用) / Execute (shared with r mode)
    """
    case_type = state.get("case_type", "both")
    memory_dir = state.get("memory_dir", "")
    outline = state.get("plan_outline")

    # 加载 skill 扩展 / Load skill extensions
    _skills_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        'skills', 'builtin',
    )
    _exts = load_skill_extensions('plan_generator', _h._settings, _skills_dir)

    # 加载 chunk 注册表 / Load chunk registry
    sections = _load_or_parse_sections(memory_dir, plan_md, outline)

    from utils.token_counter import TokenCounter
    token_counter = TokenCounter(model=_h._settings.llm_model)

    # Step 1: Section 影响分析 / Section impact analysis
    section_impact = _section_impact_analysis(feedback, case_type, token_counter, skill_extensions=_exts)
    if not any(section_impact.values()):
        logger.info(_("review.no_section_affected"))
        return plan_md

    logger.info(
        _("review.section_impact_result",
          global_sec=section_impact.get("global", False),
          single=section_impact.get("single_api", False),
          biz=section_impact.get("biz_flows", False))
    )

    # Step 2: 逐 section 做 chunk 意图分析 / Per-section chunk intent analysis
    all_actions: List[dict] = []

    if section_impact.get("global"):
        actions = _chunk_intent_for_global(feedback, token_counter, skill_extensions=_exts)
        all_actions.extend(actions)

    # section 数据直接按顶层 key 访问 / Section data accessed directly by top-level key
    # sections["single_api"] → type:"api", sections["biz_flows"] → type:"biz"
    for sec_type in ("single_api", "biz_flows"):
        if not section_impact.get(sec_type):
            continue
        sec_chunks = sections.get(sec_type, [])
        if not sec_chunks:
            continue
        actions = _chunk_intent_for_section(
            sec_chunks, sec_type, feedback, token_counter, skill_extensions=_exts,
        )
        all_actions.extend(actions)

    if not all_actions:
        logger.info(_("review.no_chunk_affected"))
        return plan_md

    # 意图分布日志 / Intent distribution log
    logger.info(_(
        "review.intent_distribution",
        total=len(all_actions),
        fix=sum(1 for a in all_actions if a.get("action") == "fix"),
        delete_chunk=sum(1 for a in all_actions if a.get("action") == "delete_chunk"),
        add=sum(1 for a in all_actions if a.get("action") == "add_chunk"),
        noop=sum(1 for a in all_actions if a.get("action") == "noop"),
    ))

    # Step 3: 执行 chunk 操作 (与 r 模式共用) / Execute (shared with r mode)
    _execute_chunk_actions(sections, all_actions, state, analysis, api_summary,
                           skill_extensions=_exts, plan_md=plan_md)

    # 保存 + 拼接 / Save + assemble
    if memory_dir:
        _save_plan_sections(memory_dir, sections)
    return _assemble_plan(sections)


# ============================================================================
# Step 1: Section 影响分析 / Section Impact Analysis
# ============================================================================


def _section_impact_analysis(
    feedback: str, case_type: str, token_counter,
    skill_extensions: List[str] | None = None,
) -> Dict[str, bool]:
    """分析用户文本反馈涉及哪些顶层 section / Determine which sections are affected.

    全英文 prompt; JSON object 输出。
    All-English prompt; JSON object output.
    """
    system_msg = render_prompt(PLAN_SECTION_IMPACT_SYSTEM)
    prompt = render_prompt(
        PLAN_SECTION_IMPACT_USER,
        feedback=feedback,
        case_type=case_type,
    )

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

    result = agent.call_llm_json(prompt, system_msg)
    # 防护：非 OpenAI 兼容 API 可能返回裸数组 / Guard: bare array from non-OpenAI APIs
    if isinstance(result, list):
        result = {}
    # 规范化输出 / Normalize output
    impact = {
        "global": bool(result.get("global", False)),
        "single_api": bool(result.get("single_api", False)),
        "biz_flows": bool(result.get("biz_flows", False)),
    }
    # case_type 约束 / Respect case_type
    if case_type == "single":
        impact["biz_flows"] = False
    elif case_type == "biz":
        impact["single_api"] = False
    return impact


# ============================================================================
# Step 2: Chunk 意图分析 (文本输入) / Chunk Intent Analysis (text input)
# ============================================================================


def _chunk_intent_for_global(
    feedback: str, token_counter,
    skill_extensions: List[str] | None = None,
) -> List[dict]:
    """分析 global section 是否需要修改 / Check if global section needs changes.

    使用简化判定 (noop vs fix) — global 只有一个"chunk"。
    Simple decision (noop vs fix) — global is effectively a single chunk.
    """
    system_msg = render_prompt(PLAN_TEXT_CHUNK_INTENT_SYSTEM)
    prompt = render_prompt(
        PLAN_TEXT_CHUNK_INTENT_USER,
        feedback=feedback,
        chunks_list="- __global__: Business Understanding (global context section)",
    )

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

    result = agent.call_llm_json_object(prompt, system_msg, "actions")
    actions = result.get("actions", [])
    if len(actions) != 1:
        logger.warning(
            _("review.intent_validation_retry",
              batch=0, attempt=1,
              errors=f"Expected 1 action for global, got {len(actions)}")
        )
        actions = []
    for a in actions:
        a["section_key"] = "__global__"
        a.setdefault("annotation", {"review_comment": feedback})
    return actions


def _chunk_intent_for_section(
    chunks: List[dict], section_type: str, feedback: str, token_counter,
    skill_extensions: List[str] | None = None,
) -> List[dict]:
    """对某个 section 的所有 chunk 做意图分析 / Intent analysis for all chunks in a section.

    输入: chunk 列表 (name + description) + 用户文本反馈
    LLM 输出: JSON object {"actions": [...]}
    """
    # 构建 chunks 描述列表 / Build chunk descriptions
    chunks_desc_parts = []
    for c in chunks:
        cid = c.get("chunk_id", c.get("key", "?"))
        cname = c.get("name", "?")
        cdesc = f"Chunk `{cid}`: {cname}"
        chunks_desc_parts.append(f"- {cdesc}")
    chunks_list = "\n".join(chunks_desc_parts)

    system_msg = render_prompt(PLAN_TEXT_CHUNK_INTENT_SYSTEM)
    prompt = render_prompt(
        PLAN_TEXT_CHUNK_INTENT_USER,
        feedback=feedback,
        chunks_list=chunks_list,
    )

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

    result = agent.call_llm_json_object(prompt, system_msg, "actions")
    actions = result.get("actions", [])
    # 数量校验 / Count validation: verify actions count matches chunk count
    expected_count = len(chunks)
    if len(actions) != expected_count:
        logger.warning(
            _("review.intent_validation_retry",
              batch=0, attempt=1,
              errors=f"Expected {expected_count} action(s), got {len(actions)}")
        )
        # fallback 为 noop / Fallback to noop for all chunks
        actions = []
    # 回填 section_key 和 annotation / Backfill section_key and annotation
    for a in actions:
        a["section_key"] = a.get("chunk_id", a.get("section_key", ""))
        a.setdefault("annotation", {"review_comment": feedback})
    return actions
