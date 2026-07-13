"""PlanGenerator: generate Markdown test plan from requirements + API defs.
支持轮廓生成 + 分块计划生成 / Supports outline generation + chunked plan generation.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from .base import BaseAgent
from config.settings import Settings
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
    PLAN_CHUNK_MERMAID_SYSTEM,
    PLAN_CHUNK_MERMAID_USER,
    PLAN_GENERATION_SYSTEM,
    PLAN_GENERATION_USER,
)
from prompts.plan_outline import PLAN_OUTLINE_SYSTEM, PLAN_OUTLINE_USER
from prompts.render import render_prompt
from i18n import get_language_name, _

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
        self._plan_single_batch_size = getattr(settings, "plan_single_batch_size", 8)
        self._plan_biz_flow_batch_size = getattr(settings, "plan_biz_flow_batch_size", 3)

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
        # 序列化接口 / Serialize interfaces
        iface_dicts = _serialize_interfaces(interfaces)

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
                _("plan_gen.input_exceeds_window",
                  tokens=input_tokens, window=self._context_window)
            )

        logger.info(
            _("plan_gen.generating", count=len(interfaces), tokens=input_tokens)
        )
        system_msg = render_prompt(PLAN_GENERATION_SYSTEM, language=get_language_name())
        plan_md = self.call_llm(prompt, system_msg)
        logger.info(_("plan_gen.generated", chars=len(plan_md)))
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

        # 获取 chunk_size 提示值（-1 时传大值）/ Get chunk size hint (-1 → large value)
        chunk_size = self._plan_single_batch_size
        if chunk_size == -1:
            chunk_size = 999

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
                _("plan_gen.outline_exceeds_window",
                  tokens=input_tokens, window=self._context_window)
            )

        logger.info(
            _("plan_gen.generating_outline",
              count=len(interface_names), tokens=input_tokens)
        )
        system_msg = render_prompt(PLAN_OUTLINE_SYSTEM, language=get_language_name())
        outline = self.call_llm_json(prompt, system_msg)
        # 确保每条记录都有唯一的 chunk_id / Ensure every entry has a unique chunk_id
        outline = _normalize_chunk_ids(outline)
        logger.info(
            _("plan_gen.outline_result",
              groups=len(outline.get("api_groups", [])),
              flows=len(outline.get("biz_flows", [])))
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
        memory_dir: str = "",
        case_type: str = "both",
    ) -> str:
        """基于轮廓分块生成完整测试计划 / Generate full plan from outline in chunks.

        Phases: A) Business Understanding + Mermaid, B) API test points per group,
        C) Biz flow tests in batches, D) Assemble.

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

        # 计算 Phase B 分组数 + Phase C 批次数 / Count groups and batches
        api_groups = outline.get("api_groups", [])
        biz_flows = outline.get("biz_flows", [])

        # Phase B: -1 时不分组（所有接口合为 1 组）/ -1 → one group for all
        single_batch = self._plan_single_batch_size
        if single_batch == -1 and api_groups:
            all_ids = []
            for g in api_groups:
                all_ids.extend(g.get("api_ids", []))
            api_groups = [{
                "group_name": "All Interfaces",
                "api_ids": all_ids,
                "test_focus": "All API endpoints",
            }]

        # Phase C: 按 plan_biz_flow_batch_size 分批 / Batch biz flows
        biz_batch = self._plan_biz_flow_batch_size
        if biz_batch == -1 or biz_batch <= 0:
            biz_batches = [biz_flows] if biz_flows else []
        else:
            biz_batches = [
                biz_flows[i:i + biz_batch]
                for i in range(0, len(biz_flows), biz_batch)
            ]

        # Resume 初始化 / Initialize resume state
        plan_parts: Dict[str, str] = {}
        if chunk_progress:
            plan_parts = chunk_progress.get("plan_parts", {})
            logger.info(_("plan_gen.resume_chunk"))

        requirement_json = json.dumps(requirement_analysis, ensure_ascii=False, indent=2)
        api_summary_json = json.dumps(api_summary or [], ensure_ascii=False, indent=2)
        outline_json = json.dumps(outline, ensure_ascii=False, indent=2)

        # Phase A: 生成 Business Understanding（仅全局上下文, 不含 Mermaid）
        # Phase A: Generate Business Understanding only (no Mermaid — per-flow below)
        global_context = self._phase_a_global(
            outline_json=outline_json,
            requirement_json=requirement_json,
            api_summary_json=api_summary_json,
            user_guidance=user_guidance,
            reference_summary=reference_summary,
            plan_parts=plan_parts,
        )

        # 逐流生成 Mermaid 图 / Per-flow Mermaid generation
        # 仅 both / biz 模式生成 / Only generate for both or biz mode
        mermaid_chunks: Dict[str, str] = {}
        if case_type in ("both", "biz"):
            for flow in biz_flows:
                self._generate_mermaid_for_flow(
                    flow=flow,
                    iface_by_id=iface_by_id,
                    outline_json=outline_json,
                    global_context=global_context,
                    plan_parts=plan_parts,
                )
            mermaid_chunks = plan_parts.get("mermaid_chunks", {})

        # Phase B: 按 API group 生成测试点 section
        # 仅 both / single 模式生成 / Only generate for both or single mode
        if case_type in ("both", "single"):
            api_sections = self._phase_b_api_sections(
                api_groups=api_groups,
                iface_by_id=iface_by_id,
                outline_json=outline_json,
                global_context=global_context,
                user_guidance=user_guidance,
                plan_parts=plan_parts,
            )
        else:
            logger.info(_("plan_gen.case_type_skip_api_sections"))
            # 跳过时返回空 dict 以匹配 Phase 返回类型与下游 .get()/in/.keys() 用法
            # Skip → empty dict to match Phase return type and downstream .get()/in/.keys() usage
            api_sections = {}

        # Phase C: 按批次生成业务链路测试 section
        # 仅 both / biz 模式生成 / Only generate for both or biz mode
        if case_type in ("both", "biz"):
            biz_sections = self._phase_c_biz_sections(
                biz_batches=biz_batches,
                iface_by_id=iface_by_id,
                outline_json=outline_json,
                global_context=global_context,
                user_guidance=user_guidance,
                plan_parts=plan_parts,
            )
        else:
            logger.info(_("plan_gen.case_type_skip_biz_sections"))
            # 跳过时返回空 dict 以匹配 Phase 返回类型与下游 .get()/in/.keys() 用法
            # Skip → empty dict to match Phase return type and downstream .get()/in/.keys() usage
            biz_sections = {}

        # 保存分块结构到 plan_sections.json / Save section structure for revision
        self._save_sections_artifact(
            memory_dir=memory_dir,
            api_groups=api_groups,
            api_sections=api_sections,
            biz_batches=biz_batches,
            biz_sections=biz_sections,
            global_context=global_context,
            mermaid_chunks=mermaid_chunks,
        )

        # ====================================================================
        # Phase D: 拼接 / Assemble
        # ====================================================================
        parts: List[str] = [global_context]

        for group in api_groups:
            section_key = f"api_{group.get('group_name', '')}"
            if section_key in api_sections:
                parts.append(api_sections[section_key])

        # Phase C 已改为批次，按 section_key 顺序添加
        # Biz sections are now batched — add in key order
        for section_key in sorted(biz_sections.keys()):
            parts.append(biz_sections[section_key])

        plan_md = "\n\n".join(parts)
        logger.info(
            _("plan_gen.assembled", chunks=len(parts), chars=len(plan_md))
        )
        return plan_md


    # -----------------------------------------------------------------------
    # Phase 私有方法 / Private phase methods
    # -----------------------------------------------------------------------

    def _phase_a_global(
        self,
        outline_json: str,
        requirement_json: str,
        api_summary_json: str,
        user_guidance: str,
        reference_summary: str,
        plan_parts: Dict[str, str],
    ) -> str:
        """Phase A: 生成 Business Understanding + Mermaid / Generate global context section.

        如果 plan_parts 中已有 global_context (resume), 则直接返回。
        """
        global_context = plan_parts.get("global_context", "")
        if global_context:
            return global_context

        prompt = render_prompt(
            PLAN_CHUNK_GLOBAL_USER,
            outline=outline_json,
            requirement_analysis=requirement_json,
            api_summary=api_summary_json,
            user_guidance=user_guidance or "(none)",
            reference_summary=reference_summary or "(none)",
            language=get_language_name(),
        )
        self.reset_steps()
        system_msg = render_prompt(
            PLAN_CHUNK_GLOBAL_SYSTEM,
            outline=outline_json,
            language=get_language_name(),
        )
        global_context = self.call_llm(prompt, system_msg)
        plan_parts["global_context"] = global_context
        logger.info(_("plan_gen.phase_a_done"))
        return global_context

    def _generate_mermaid_for_flow(
        self,
        flow: Dict[str, Any],
        iface_by_id: Dict[str, dict],
        outline_json: str,
        global_context: str,
        plan_parts: Dict[str, Any],
    ) -> str:
        """为单个业务流生成 Mermaid 序列图 / Generate Mermaid diagram for one biz flow.

        Mermaid 内容存入 plan_parts["mermaid_chunks"][chunk_id]，
        后续 _save_sections_artifact 将其合并到对应 biz chunk。
        Mermaid content stored in plan_parts["mermaid_chunks"][chunk_id],
        later merged into the biz chunk by _save_sections_artifact.
        """
        chunk_id = flow.get("chunk_id", "")
        flow_name = flow.get("name", "")

        # Resume 检查 / Resume check
        mermaid_chunks = plan_parts.get("mermaid_chunks", {})
        if chunk_id in mermaid_chunks:
            return mermaid_chunks[chunk_id]

        api_ids = flow.get("involved_apis", [])
        flow_ifaces = [iface_by_id[aid] for aid in api_ids if aid in iface_by_id]

        prompt = render_prompt(
            PLAN_CHUNK_MERMAID_USER,
            flow_name=flow_name,
            flow_description=flow.get("description", ""),
            interface_defs=json.dumps(flow_ifaces, ensure_ascii=False, indent=2),
        )
        system_msg = render_prompt(
            PLAN_CHUNK_MERMAID_SYSTEM,
            flow_name=flow_name,
            flow_description=flow.get("description", ""),
            flow_api_ids=", ".join(api_ids),
            global_context=global_context,
            language=get_language_name(),
        )
        self.reset_steps()
        mermaid_content = self.call_llm(prompt, system_msg)

        plan_parts.setdefault("mermaid_chunks", {})[chunk_id] = mermaid_content
        logger.info(_("plan_gen.mermaid_generated", flow=flow_name))
        return mermaid_content

    def _phase_b_api_sections(
        self,
        api_groups: List[dict],
        iface_by_id: Dict[str, dict],
        outline_json: str,
        global_context: str,
        user_guidance: str,
        plan_parts: Dict[str, Any],
    ) -> Dict[str, str]:
        """Phase B: 按 API group 逐个生成测试点 / Generate API test sections per group.

        已完成的 group (resume) 自动跳过。
        """
        api_sections = plan_parts.get("api_sections", {})
        if isinstance(api_sections, str):
            api_sections = json.loads(api_sections)
        plan_parts.setdefault("api_sections", {})

        for i, group in enumerate(api_groups):
            group_name = group.get("group_name", f"group_{i}")
            section_key = f"api_{group_name}"
            if section_key in api_sections:
                continue

            # 收集该 group 的接口定义 / Collect interface defs for this group
            group_api_ids = group.get("api_ids", [])
            group_ifaces = [iface_by_id[aid] for aid in group_api_ids if aid in iface_by_id]

            prompt = render_prompt(
                PLAN_CHUNK_API_SECTION_USER,
                interface_defs=json.dumps(group_ifaces, ensure_ascii=False, indent=2),
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
                _("plan_gen.phase_b_chunk",
                  current=i + 1, total=len(api_groups),
                  name=group_name, count=len(group_ifaces))
            )
            self.reset_steps()
            section_md = self.call_llm(prompt, system_with_context)
            api_sections[section_key] = section_md

        plan_parts["api_sections"] = api_sections
        return api_sections

    def _phase_c_biz_sections(
        self,
        biz_batches: List[List[dict]],
        iface_by_id: Dict[str, dict],
        outline_json: str,
        global_context: str,
        user_guidance: str,
        plan_parts: Dict[str, Any],
    ) -> Dict[str, str]:
        """Phase C: 按批次生成业务链路测试 / Generate biz flow test sections in batches.

        已完成的批次 (resume) 自动跳过。接口按 batch 去重收集。
        """
        biz_sections = plan_parts.get("biz_sections", {})
        if isinstance(biz_sections, str):
            biz_sections = json.loads(biz_sections)
        plan_parts.setdefault("biz_sections", {})

        for j, batch in enumerate(biz_batches):
            if not batch:
                continue

            # 构造本批次的 key（首 flow 名 + 数量）/ Build batch key (first flow name + count)
            first_name = batch[0].get("name", f"flow_{j}")
            if len(batch) == 1:
                section_key = f"biz_{first_name}"
                flow_names = first_name
            else:
                section_key = f"biz_batch_{j}"
                flow_names = ", ".join(f.get("name", "?") for f in batch)

            if section_key in biz_sections:
                continue

            # 收集本批次所有相关接口（去重）/ Collect relevant interfaces (deduped)
            seen_ids = set()
            batch_ifaces = []
            for flow in batch:
                for aid in flow.get("involved_apis", []):
                    if aid not in seen_ids and aid in iface_by_id:
                        seen_ids.add(aid)
                        batch_ifaces.append(iface_by_id[aid])

            # 构造 flows_list 用于 prompt / Build flows_list for prompt
            flows_desc = []
            for flow in batch:
                flows_desc.append(
                    f"- Name: {flow.get('name', '?')}\n"
                    f"  Description: {flow.get('description', '')}\n"
                    f"  APIs: {', '.join(flow.get('involved_apis', []))}"
                )
            flows_list = "\n\n".join(flows_desc)

            prompt = render_prompt(
                PLAN_CHUNK_BIZ_SECTION_USER,
                interface_defs=json.dumps(batch_ifaces, ensure_ascii=False, indent=2),
                user_guidance=user_guidance or "(none)",
                language=get_language_name(),
            )

            system_with_context = render_prompt(
                PLAN_CHUNK_BIZ_SECTION_SYSTEM,
                outline=outline_json,
                global_context=global_context,
                flows_list=flows_list,
                language=get_language_name(),
            )

            # 日志：单 flow vs 批量 / Log: single vs batch
            if len(batch) == 1:
                logger.info(
                    _("plan_gen.phase_c_chunk",
                      current=j + 1, total=len(biz_batches), name=flow_names)
                )
            else:
                logger.info(
                    _("plan_gen.phase_c_batch",
                      current=j + 1, total=len(biz_batches),
                      names=flow_names, count=len(batch))
                )

            self.reset_steps()
            section_md = self.call_llm(prompt, system_with_context)
            biz_sections[section_key] = section_md

        plan_parts["biz_sections"] = biz_sections
        return biz_sections

    def _save_sections_artifact(
        self,
        memory_dir: str,
        api_groups: List[dict],
        api_sections: Dict[str, str],
        biz_batches: List[List[dict]],
        biz_sections: Dict[str, str],
        global_context: str,
        mermaid_chunks: Dict[str, str] | None = None,
    ):
        """保存分块结构到 plan_sections.json / Save section structure for revision.

        转换 plan_parts (flat dicts) 为有序 sections 数组并持久化。
        Mermaid 内容直接存入对应 biz chunk 的 mermaid 字段。
        Mermaid content stored directly in the biz chunk's mermaid field.
        """
        if not memory_dir:
            return

        from graph.nodes.helpers import save_pipeline_artifact

        mermaid_map = mermaid_chunks or {}
        _sections = []
        # API groups / 接口分组 (使用 chunk_id)
        # API groups (use chunk_id as key)
        for group in api_groups:
            chunk_id = group.get("chunk_id", "")
            # _phase_b_api_sections 用 f"api_{group_name}" 作 key
            # _phase_b_api_sections uses f"api_{group_name}" as key
            section_key = f"api_{group.get('group_name', '')}"
            content = api_sections.get(section_key, "")
            if content and content.strip():
                _sections.append({
                    "chunk_id": f"api_{chunk_id}" if chunk_id else section_key,
                    "key": f"api_{chunk_id}" if chunk_id else section_key,
                    "type": "api",
                    "name": group.get("group_name", ""),
                    "section": "single_api",
                    "content": content,
                })
        # Biz flows / 业务流 (使用 chunk_id, 绑定 Mermaid)
        # Biz flows (use chunk_id, bind Mermaid)
        for j, batch in enumerate(biz_batches):
            if not batch:
                continue
            for flow in batch:
                chunk_id = flow.get("chunk_id", f"flow_{j}")
                biz_key = f"biz_{chunk_id}"
                # _phase_c_biz_sections 用 f"biz_{flow_name}" 或 f"biz_batch_{j}" 作 key
                # _phase_c_biz_sections uses f"biz_{flow_name}" or f"biz_batch_{j}" as key
                if len(batch) == 1:
                    section_key = f"biz_{flow.get('name', '')}"
                else:
                    section_key = f"biz_batch_{j}"
                content = biz_sections.get(section_key, "")
                if content and content.strip():
                    _sections.append({
                        "chunk_id": biz_key,
                        "key": biz_key,
                        "type": "biz",
                        "name": flow.get("name", ""),
                        "section": "biz_flows",
                        "content": content,
                        "mermaid": mermaid_map.get(chunk_id, ""),
                    })
        save_pipeline_artifact(memory_dir, "plan_sections.json", {
            "global": global_context,
            "sections": _sections,
        })


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


def _name_to_chunk_id(name: str, prefix: str = "") -> str:
    """将中文/英文名称转为安全的 ASCII chunk_id / Convert name to safe ASCII chunk_id.

    移除非 ASCII 字符，空格/特殊符号替换为下划线，小写。
    Remove non-ASCII chars, replace spaces/symbols with underscores, lowercase.
    """
    import unicodedata
    # 尝试拼音首字母提取 / Try extracting first letters of pinyin
    # 对于纯中文名，尝试用 unicodedata 规范化后取 ASCII 部分
    # For pure Chinese names, normalize and extract ASCII portions
    normalized = unicodedata.normalize('NFKD', name)
    ascii_part = normalized.encode('ascii', 'ignore').decode('ascii')
    if ascii_part.strip():
        safe = re.sub(r'[^a-zA-Z0-9]+', '_', ascii_part).strip('_').lower()
    else:
        # 纯中文名 / Pure Chinese name — just strip and lowercase anything usable
        safe = re.sub(r'[^a-zA-Z0-9]+', '_', name).strip('_').lower()
    # 清理多余的连续下划线 / Collapse multiple underscores
    safe = re.sub(r'_+', '_', safe)
    if prefix and not safe.startswith(prefix):
        safe = prefix + safe
    return safe or (prefix + "chunk")


def _normalize_chunk_ids(outline: Dict[str, Any]) -> Dict[str, Any]:
    """确保轮廓中所有条目有唯一 chunk_id / Ensure every outline entry has a unique chunk_id.

    若 LLM 未生成 chunk_id 则自动补全; 去重冲突检测。
    Auto-generates missing chunk_ids; detects and resolves collisions.
    """
    seen: set = set()

    for i, group in enumerate(outline.get("api_groups", [])):
        cid = group.get("chunk_id", "").strip()
        if not cid:
            cid = _name_to_chunk_id(group.get("group_name", f"group_{i}"), prefix="api_")
        if not cid.startswith("api_"):
            cid = "api_" + cid
        # 去重 / Deduplicate
        original = cid
        suffix = 0
        while cid in seen:
            suffix += 1
            cid = f"{original}_{suffix}"
        seen.add(cid)
        group["chunk_id"] = cid

    for j, flow in enumerate(outline.get("biz_flows", [])):
        cid = flow.get("chunk_id", "").strip()
        if not cid:
            cid = _name_to_chunk_id(flow.get("name", f"flow_{j}"), prefix="biz_")
        if not cid.startswith("biz_"):
            cid = "biz_" + cid
        # 去重 / Deduplicate
        original = cid
        suffix = 0
        while cid in seen:
            suffix += 1
            cid = f"{original}_{suffix}"
        seen.add(cid)
        flow["chunk_id"] = cid

    return outline
