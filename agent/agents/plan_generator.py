"""PlanGenerator: generate Markdown test plan from requirements + API defs.
支持轮廓生成 + 分块计划生成 / Supports outline generation + chunked plan generation.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from .base import BaseAgent
from config.settings import Settings, get_strategy
from knowledge.search import KnowledgeSearch
from models.schema import InterfaceDef
from prompts import KNOWLEDGE_SECTION_HEADER
from prompts.plan_generation import (
    PLAN_CHUNK_API_SECTION_SYSTEM,
    PLAN_CHUNK_API_SECTION_USER,
    PLAN_CHUNK_BIZ_SECTION_SYSTEM,
    PLAN_CHUNK_BIZ_SECTION_USER,
    PLAN_CHUNK_GLOBAL_SYSTEM,
    PLAN_CHUNK_GLOBAL_USER,
    PLAN_GENERATION_SYSTEM,
    PLAN_GENERATION_USER,
)
from prompts.plan_outline import PLAN_OUTLINE_SYSTEM, PLAN_OUTLINE_USER
from prompts.render import render_prompt
from i18n import get_language_name

logger = logging.getLogger(__name__)


class PlanGenerator(BaseAgent):
    """Generate a test plan in Markdown format combining requirements and API docs."""

    def __init__(self, settings: Settings, knowledge: Optional[KnowledgeSearch] = None, skill_extensions: List[str] = None):
        super().__init__(
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            max_retries=settings.max_retries,
            max_steps=settings.max_steps,
            base_url=settings.llm_base_url,
            context_window=settings.llm_context_window,
            max_output_tokens=settings.llm_max_output_tokens,
            compression_threshold=settings.llm_context_compression_threshold,
            skill_extensions=skill_extensions,
        )
        self._knowledge = knowledge
        self._plan_chunk_size = getattr(settings, "plan_chunk_size", 8)

    def generate(
        self,
        requirement_analysis: Dict[str, Any],
        interfaces: List[InterfaceDef],
        api_summary: List[Dict[str, Any]] | None = None,
        user_guidance: str = "",
        reference_summary: str = "",
    ) -> str:
        """Generate a Markdown test plan.

        Args:
            requirement_analysis: Structured analysis from RequirementAnalyzer.
            interfaces: List of InterfaceDef objects or dicts.
            api_summary: Optional API analysis summary from ApiAnalyzer.
            user_guidance: Optional user guidance from --prompt CLI flag.
            reference_summary: Optional summary of existing coverage from --reference-dir.

        Returns the full plan as a Markdown string.
        """
        # Serialize interfaces
        iface_dicts = []
        for iface in interfaces:
            if isinstance(iface, dict):
                iface_dicts.append(iface)
            else:
                iface_dicts.append({
                    "test_id": iface.test_id,
                    "api_name": iface.api_name,
                    "app_name": iface.app_name,
                    "method": iface.method,
                    "url": iface.url,
                    "request_head": iface.request_head,
                    "request_body": iface.request_body,
                    "status_code": iface.status_code,
                    "assert_dict": iface.assert_dict,
                    "remark": iface.remark,
                })

        requirement_json = json.dumps(requirement_analysis, ensure_ascii=False, indent=2)
        iface_json = json.dumps(iface_dicts, ensure_ascii=False, indent=2)
        api_summary_json = json.dumps(api_summary, ensure_ascii=False, indent=2) if api_summary else "No API analysis summary"

        prompt = render_prompt(
            PLAN_GENERATION_USER,
            requirement_analysis=requirement_json,
            interface_defs=iface_json,
            api_summary=api_summary_json,
            user_guidance=user_guidance,
            reference_summary=reference_summary or "(none)",
            language=get_language_name(),
        )

        # Conditionally append knowledge context
        if self._knowledge is not None:
            docs = self._knowledge.search("test plan generation best practices", n_results=3)
            if docs:
                knowledge_context = "\n---\n".join(docs)
                prompt += f"\n\n{KNOWLEDGE_SECTION_HEADER}{knowledge_context}"

        # Token check
        input_tokens = self._estimate_input_tokens(PLAN_GENERATION_SYSTEM, prompt)
        if input_tokens > self._context_window:
            raise ValueError(
                f"Plan generation input exceeds context window: "
                f"{input_tokens} / {self._context_window} tokens. "
                f"Consider reducing the number of interfaces or splitting the task."
            )

        logger.info(
            "Generating test plan for %d interfaces (~%d tokens)...",
            len(interfaces), input_tokens,
        )
        plan_md = self.call_llm(prompt, PLAN_GENERATION_SYSTEM)
        logger.info("Test plan generated (%d chars)", len(plan_md))
        return plan_md

    def generate_outline(
        self,
        requirement_analysis: Dict[str, Any],
        interface_names: List[Dict[str, str]],
        api_summary: List[Dict[str, Any]] | None = None,
        user_guidance: str = "",
    ) -> Dict[str, Any]:
        """生成测试计划轮廓 JSON / Generate a lightweight test plan outline (JSON).

        轮廓用于指导后续分块计划生成。输入仅包含接口名称/URL，
        不含完整 request/response body，确保输出不被截断。

        The outline guides subsequent chunked plan generation. Input uses only
        interface names/URLs (no full bodies), guaranteeing no truncation.

        Args:
            requirement_analysis: 需求分析结果 / Structured requirement analysis.
            interface_names: 轻量接口列表 / Lightweight interface list (test_id, api_name, method, url).
            api_summary: 可选接口分析摘要 / Optional API analysis summary.
            user_guidance: 用户通过 --prompt 传入的指导 / User guidance from --prompt.

        Returns:
            outline dict with api_groups, biz_flows, business_summary.
        """
        requirement_json = json.dumps(requirement_analysis, ensure_ascii=False, indent=2)
        iface_json = json.dumps(interface_names, ensure_ascii=False, indent=2)
        api_summary_json = json.dumps(api_summary or [], ensure_ascii=False, indent=2)

        # 获取 chunk_size 提示值 / Get chunk size hint for the prompt
        chunk_size = getattr(self, "_plan_chunk_size", 8)

        prompt = render_prompt(
            PLAN_OUTLINE_USER,
            requirement_analysis=requirement_json,
            interface_names=iface_json,
            api_summary=api_summary_json,
            user_guidance=user_guidance or "(none)",
            language=get_language_name(),
            chunk_size_hint=str(chunk_size),
        )

        # Token 检查 / Token limit check
        input_tokens = self._estimate_input_tokens(PLAN_OUTLINE_SYSTEM, prompt)
        if input_tokens > self._context_window:
            raise ValueError(
                f"Outline generation input exceeds context window: "
                f"{input_tokens} / {self._context_window} tokens."
            )

        logger.info(
            "Generating test plan outline for %d interfaces (~%d tokens)...",
            len(interface_names), input_tokens,
        )
        outline = self.call_llm_json(prompt, PLAN_OUTLINE_SYSTEM)
        logger.info(
            "Outline generated: %d API groups, %d biz flows",
            len(outline.get("api_groups", [])),
            len(outline.get("biz_flows", [])),
        )
        return outline

    def generate_from_outline(
        self,
        outline: Dict[str, Any],
        requirement_analysis: Dict[str, Any],
        interfaces: List[Any],
        api_summary: List[Dict[str, Any]] | None = None,
        user_guidance: str = "",
        reference_summary: str = "",
        chunk_progress: Dict[str, Any] | None = None,
    ) -> str:
        """基于轮廓分块生成完整测试计划 / Generate full plan from outline in chunks.

        Phases: A) Business Understanding + Mermaid, B) API test points per group,
        C) Biz flow tests per flow, D) Assemble.

        Args:
            outline: 测试计划轮廓 / Plan outline JSON.
            requirement_analysis: 需求分析结果 / Requirement analysis.
            interfaces: 完整接口定义列表 / Full interface definitions.
            api_summary: 接口分析摘要 / API analysis summaries.
            user_guidance: 用户指导 / User guidance.
            reference_summary: 增量更新参考摘要 / Reference coverage summary.
            chunk_progress: Resume 时的进度 / Chunk progress for resume.

        Returns:
            完整 plan.md 字符串 / Complete plan.md string.
        """
        # 序列化接口 / Serialize interfaces
        iface_dicts = _serialize_interfaces(interfaces)
        iface_by_id = {d["test_id"]: d for d in iface_dicts if d.get("test_id")}

        # Resume 初始化 / Initialize resume state
        plan_parts: Dict[str, str] = {}
        completed_chunks = 0
        total_chunks = 1 + len(outline.get("api_groups", [])) + len(outline.get("biz_flows", []))
        if chunk_progress:
            plan_parts = chunk_progress.get("plan_parts", {})
            completed_chunks = chunk_progress.get("completed_chunks", 0)
            logger.info(
                "Resuming from chunk %d/%d", completed_chunks + 1, total_chunks
            )

        requirement_json = json.dumps(requirement_analysis, ensure_ascii=False, indent=2)
        api_summary_json = json.dumps(api_summary or [], ensure_ascii=False, indent=2)

        # ====================================================================
        # Phase A: 生成 Business Understanding + Mermaid（全局视角）
        # ====================================================================
        global_context = plan_parts.get("global_context", "")
        if not global_context:
            outline_json = json.dumps(outline, ensure_ascii=False, indent=2)
            prompt = render_prompt(
                PLAN_CHUNK_GLOBAL_USER,
                outline=outline_json,
                requirement_analysis=requirement_json,
                api_summary=api_summary_json,
                user_guidance=user_guidance or "(none)",
                reference_summary=reference_summary or "(none)",
                language=get_language_name(),
            )
            global_context = self.call_llm(prompt, PLAN_CHUNK_GLOBAL_SYSTEM)
            plan_parts["global_context"] = global_context
            completed_chunks += 1
            logger.info("Phase A complete: Business Understanding + Mermaid")

        # ====================================================================
        # Phase B: 逐 API group 生成测试点 section
        # ====================================================================
        api_sections = plan_parts.get("api_sections", {})
        if isinstance(api_sections, str):
            api_sections = json.loads(api_sections)
        plan_parts.setdefault("api_sections", {})

        for i, group in enumerate(outline.get("api_groups", [])):
            group_name = group.get("group_name", f"group_{i}")
            section_key = f"api_{group_name}"
            if section_key in api_sections:
                completed_chunks += 1
                continue

            # 收集该 group 的接口定义 / Collect interface defs for this group
            group_api_ids = group.get("api_ids", [])
            group_ifaces = [iface_by_id[aid] for aid in group_api_ids if aid in iface_by_id]
            group_iface_json = json.dumps(group_ifaces, ensure_ascii=False, indent=2)

            outline_json = json.dumps(outline, ensure_ascii=False, indent=2)
            prompt = render_prompt(
                PLAN_CHUNK_API_SECTION_USER,
                interface_defs=group_iface_json,
                user_guidance=user_guidance or "(none)",
                language=get_language_name(),
            )

            # 注入全局上下文 / Inject global context into system prompt
            system_with_context = render_prompt(
                PLAN_CHUNK_API_SECTION_SYSTEM,
                outline=outline_json,
                global_context=global_context,
                group_name=group_name,
                test_focus=group.get("test_focus", ""),
                group_api_ids=json.dumps(group_api_ids),
                language=get_language_name(),
            )

            logger.info(
                "Phase B chunk %d/%d: %s (%d interfaces)",
                i + 1, len(outline.get("api_groups", [])),
                group_name, len(group_ifaces),
            )
            section_md = self.call_llm(prompt, system_with_context)
            api_sections[section_key] = section_md
            completed_chunks += 1

        plan_parts["api_sections"] = api_sections

        # ====================================================================
        # Phase C: 逐 biz flow 生成流程测试 section
        # ====================================================================
        biz_sections = plan_parts.get("biz_sections", {})
        if isinstance(biz_sections, str):
            biz_sections = json.loads(biz_sections)
        plan_parts.setdefault("biz_sections", {})

        for j, flow in enumerate(outline.get("biz_flows", [])):
            flow_name = flow.get("name", f"flow_{j}")
            section_key = f"biz_{flow_name}"
            if section_key in biz_sections:
                completed_chunks += 1
                continue

            # 收集相关接口定义 / Collect relevant interface defs
            flow_api_ids = flow.get("involved_apis", [])
            flow_ifaces = [iface_by_id[aid] for aid in flow_api_ids if aid in iface_by_id]
            flow_iface_json = json.dumps(flow_ifaces, ensure_ascii=False, indent=2)

            outline_json = json.dumps(outline, ensure_ascii=False, indent=2)
            prompt = render_prompt(
                PLAN_CHUNK_BIZ_SECTION_USER,
                interface_defs=flow_iface_json,
                user_guidance=user_guidance or "(none)",
                language=get_language_name(),
            )

            system_with_context = render_prompt(
                PLAN_CHUNK_BIZ_SECTION_SYSTEM,
                outline=outline_json,
                global_context=global_context,
                flow_name=flow_name,
                flow_description=flow.get("description", ""),
                flow_api_ids=json.dumps(flow_api_ids),
                language=get_language_name(),
            )

            logger.info(
                "Phase C chunk %d/%d: %s",
                j + 1, len(outline.get("biz_flows", [])), flow_name,
            )
            section_md = self.call_llm(prompt, system_with_context)
            biz_sections[section_key] = section_md
            completed_chunks += 1

        plan_parts["biz_sections"] = biz_sections

        # ====================================================================
        # Phase D: 拼接 / Assemble
        # ====================================================================
        parts: List[str] = [global_context]

        for group in outline.get("api_groups", []):
            section_key = f"api_{group.get('group_name', '')}"
            if section_key in api_sections:
                parts.append(api_sections[section_key])

        for flow in outline.get("biz_flows", []):
            section_key = f"biz_{flow.get('name', '')}"
            if section_key in biz_sections:
                parts.append(biz_sections[section_key])

        plan_md = "\n\n".join(parts)
        logger.info(
            "Plan assembled: %d chunks, %d chars",
            len(parts), len(plan_md),
        )
        return plan_md


# ---------------------------------------------------------------------------
# 模块级辅助 / Module-level helpers
# ---------------------------------------------------------------------------

def _serialize_interfaces(interfaces: List[Any]) -> List[Dict[str, Any]]:
    """序列化接口定义列表 / Serialize interface def list to dicts."""
    result = []
    for iface in interfaces:
        if isinstance(iface, dict):
            result.append(iface)
        else:
            result.append({
                "test_id": getattr(iface, "test_id", ""),
                "api_name": getattr(iface, "api_name", ""),
                "app_name": getattr(iface, "app_name", ""),
                "method": getattr(iface, "method", "GET"),
                "url": getattr(iface, "url", ""),
                "request_head": getattr(iface, "request_head", {}),
                "request_body": getattr(iface, "request_body", {}),
                "status_code": getattr(iface, "status_code", 200),
                "assert_dict": getattr(iface, "assert_dict", {}),
                "remark": getattr(iface, "remark", ""),
            })
    return result
