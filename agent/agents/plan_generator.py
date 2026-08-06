"""PlanGenerator: generate Markdown test plan from requirements + API defs.
支持轮廓生成 + 分块计划生成 / Supports outline generation + chunked plan generation.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
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
from utils.progress import ProgressTracker

logger = logging.getLogger(__name__)


class PlanGenerator(BaseAgent):
    """Generate a test plan in Markdown format combining requirements and API docs."""

    def __init__(self, settings: Settings, knowledge: Optional[KnowledgeSearch] = None, skill_extensions: List[str] = None):
        super().__init__(
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            temperature=settings.llm_temperature,
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
        system_msg = render_prompt(
            PLAN_OUTLINE_SYSTEM,
            language=get_language_name(),
            chunk_size_hint=str(chunk_size),
        )
        outline = self.call_llm_json_object(prompt, system_msg, "api_groups")
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
            # v2 轻量格式：从 plan_sections.json 重建 plan_parts / v2 lightweight: reconstruct from plan_sections.json
            if chunk_progress.get("version") == 2:
                plan_parts = self._reconstruct_plan_parts(memory_dir, outline, chunk_progress)
                logger.info(_("plan_gen.resume_chunk_v2",
                              phase_a=chunk_progress.get("phase_a_done"),
                              api=len(chunk_progress.get("api_group_completed_ids", [])),
                              biz=len(chunk_progress.get("biz_batch_completed_keys", []))))
            else:
                # v1 旧格式（向后兼容）/ v1 legacy format (backward compatible)
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
        # 保存 chunk 进度（Phase A 完成后）/ Save chunk progress after Phase A
        self._save_chunk_progress(memory_dir, plan_parts, api_groups=api_groups, biz_batches=biz_batches)

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
                memory_dir=memory_dir,
            )
        else:
            logger.info(_("plan_gen.case_type_skip_api_sections"))
            api_sections = {}

        # Phase C: 按批次生成业务链路测试 section（Mermaid + 用例内容）
        # 仅 both / biz 模式生成 / Only generate for both or biz mode
        # Mermaid 在 Phase C 内部逐流生成，与 biz content 天然捆绑
        # Mermaid is generated per-flow within Phase C, naturally bundled with biz content
        if case_type in ("both", "biz"):
            biz_sections = self._phase_c_biz_sections(
                biz_batches=biz_batches,
                iface_by_id=iface_by_id,
                outline_json=outline_json,
                global_context=global_context,
                user_guidance=user_guidance,
                plan_parts=plan_parts,
                memory_dir=memory_dir,
                api_groups=api_groups,
            )
        else:
            logger.info(_("plan_gen.case_type_skip_biz_sections"))
            biz_sections = {}

        # 保存分块结构到 plan_sections.json / Save section structure for revision
        self._save_sections_artifact(
            memory_dir=memory_dir,
            api_groups=api_groups,
            api_sections=api_sections,
            biz_batches=biz_batches,
            biz_sections=biz_sections,
            global_context=global_context,
        )

        # ====================================================================
        # Phase D: 拼接 plan.md / Assemble plan.md
        # 使用 shared assemble_plan_md 统一处理 heading 和 mermaid 顺序
        # Use shared assemble_plan_md for unified heading & mermaid ordering
        # ====================================================================
        from flow_forge_schemas.plan_sections import assemble_plan_md

        # 构建临时 sections 结构供 assemble_plan_md 使用
        # Build temporary sections structure for assemble_plan_md
        plan_lang = get_language_name()
        temp_sections: dict = {
            "business_understanding": {
                "chunk_id": "business_understanding",
                "content": global_context,
            },
            "single_api": [],
            "biz_flows": [],
        }

        for group in api_groups:
            section_key = group.get("chunk_id", "") or f"api_{group.get('group_name', '')}"
            if section_key and section_key in api_sections:
                temp_sections["single_api"].append({
                    "chunk_id": section_key,
                    "content": api_sections[section_key],
                })

        for section_key in sorted(biz_sections.keys()):
            entry = biz_sections[section_key]
            if isinstance(entry, dict):
                content = entry.get("content", "")
                mermaids_dict = entry.get("mermaids", {})
                mermaid_parts = [m.strip() for m in mermaids_dict.values() if m and m.strip()]
                combined_mermaid = "\n\n".join(mermaid_parts)
                temp_sections["biz_flows"].append({
                    "chunk_id": section_key,
                    "content": content,
                    "mermaid": combined_mermaid,
                })
            else:
                temp_sections["biz_flows"].append({
                    "chunk_id": section_key,
                    "content": entry,
                    "mermaid": "",
                })

        plan_md = assemble_plan_md(temp_sections, language=plan_lang)
        logger.info(
            _("plan_gen.assembled", chunks=len(temp_sections["single_api"]) + len(temp_sections["biz_flows"]) + 1, chars=len(plan_md))
        )
        return plan_md


    # -----------------------------------------------------------------------
    # Chunk 进度持久化 / Chunk progress persistence
    # -----------------------------------------------------------------------

    def _save_chunk_progress(self, memory_dir: str, plan_parts: Dict[str, Any],
                             api_groups: List[dict] = None,
                             biz_batches: List[List[dict]] = None,
                             api_tracker: ProgressTracker = None,
                             biz_tracker: ProgressTracker = None) -> None:
        """保存 chunk 进度（轻量格式）并增量保存 plan_sections.json。

        Save lightweight chunk progress + incremental plan_sections.json.
        使用 ProgressTracker 统一进度表示。
        Uses ProgressTracker for unified progress representation.

        进度文件仅记录阶段完成状态和已完成的 chunk ID 列表，不重复存储内容；
        内容由 plan_sections.json（增量保存）提供。
        Progress file only records phase status and completed chunk IDs, no content;
        content comes from plan_sections.json (saved incrementally).
        """
        if not memory_dir:
            return

        # 提取轻量进度信息 / Extract lightweight progress info
        api_sections_data = plan_parts.get("api_sections", {})
        if isinstance(api_sections_data, str):
            try:
                api_sections_data = json.loads(api_sections_data)
            except (json.JSONDecodeError, TypeError):
                api_sections_data = {}
        biz_sections_data = plan_parts.get("biz_sections", {})
        if isinstance(biz_sections_data, str):
            try:
                biz_sections_data = json.loads(biz_sections_data)
            except (json.JSONDecodeError, TypeError):
                biz_sections_data = {}

        # 使用 ProgressTracker 构建进度 / Build progress using ProgressTracker
        progress: Dict[str, Any] = {"version": 2}

        if api_tracker is not None:
            api_light = api_tracker.to_lightweight_dict()
            # 兼容旧 key 名 / Backward-compatible key name
            progress["api_group_completed_ids"] = api_light["completed_ids"]
        else:
            progress["api_group_completed_ids"] = (
                list(api_sections_data.keys()) if isinstance(api_sections_data, dict) else [])
        progress["phase_a_done"] = bool(plan_parts.get("global_context", ""))

        # biz 进度单独字段 / biz progress in separate field
        if biz_tracker is not None:
            biz_light = biz_tracker.to_lightweight_dict()
            progress["biz_batch_completed_keys"] = biz_light["completed_ids"]
        else:
            progress["biz_batch_completed_keys"] = (
                list(biz_sections_data.keys()) if isinstance(biz_sections_data, dict) else [])

        progress_path = Path(memory_dir) / "plan_chunks_progress.json"
        progress_path.parent.mkdir(parents=True, exist_ok=True)
        progress_path.write_text(
            json.dumps(progress, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # 增量保存 plan_sections.json 用于 resume 时恢复内容
        # Save plan_sections.json incrementally for content recovery on resume
        if api_groups is not None:
            global_context = plan_parts.get("global_context", "")
            self._save_sections_artifact(
                memory_dir, api_groups or [], api_sections_data if isinstance(api_sections_data, dict) else {},
                biz_batches or [], biz_sections_data if isinstance(biz_sections_data, dict) else {},
                global_context,
            )

    def _reconstruct_plan_parts(
        self, memory_dir: str, outline: Dict[str, Any],
        progress: Dict[str, Any],
    ) -> Dict[str, Any]:
        """从 plan_sections.json + outline + progress 重建 plan_parts。

        Reconstruct plan_parts dict from saved content and progress for resume.
        仅在 v2 轻量格式下使用；v1 旧格式直接返回 plan_parts 内容。
        Only used for v2 lightweight format; v1 returns plan_parts content directly.
        """
        sections_path = Path(memory_dir) / "plan_sections.json"
        if not sections_path.exists():
            return {}

        try:
            sections = json.loads(sections_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

        plan_parts: Dict[str, Any] = {}

        # Phase A: global context
        bu = sections.get("business_understanding", "")
        # 兼容新旧格式 / Compatible with old (str) and new (dict) format
        if isinstance(bu, dict):
            bu_text = bu.get("content", "")
        else:
            bu_text = bu
        if progress.get("phase_a_done") and bu_text:
            plan_parts["global_context"] = bu_text

        # Phase B: 将 single_api 数组映射回 api_sections dict / Map single_api array back to api_sections
        api_groups = outline.get("api_groups", [])
        completed_api_ids = set(progress.get("api_group_completed_ids", []))
        if api_groups and completed_api_ids:
            # 构建 plan_sections.json 中 section 的查找表 / Build lookup from plan_sections.json
            sections_by_key: Dict[str, dict] = {}
            for sec in sections.get("single_api", []):
                for k in ("key", "chunk_id"):
                    v = sec.get(k, "")
                    if v:
                        sections_by_key[v] = sec

            api_sections: Dict[str, str] = {}
            for group in api_groups:
                section_key = group.get("chunk_id", f"api_{group.get('group_name', '')}")
                if section_key in completed_api_ids:
                    chunk_id = group.get("chunk_id", "")
                    sec = sections_by_key.get(chunk_id) or sections_by_key.get(section_key)
                    if sec and sec.get("content", "").strip():
                        api_sections[section_key] = sec["content"]
            if api_sections:
                plan_parts["api_sections"] = api_sections

        # Phase C: 将 biz_flows 数组映射回 biz_sections + mermaid_chunks
        # Map biz_flows array back to biz_sections + mermaid_chunks
        biz_batches = outline.get("biz_flows", [])
        completed_biz_keys = set(progress.get("biz_batch_completed_keys", []))
        if biz_batches and completed_biz_keys:
            # 按 batch_size 分组以匹配原 section_key / Group by batch_size to match original section_key
            biz_batch_size = getattr(self, '_plan_biz_flow_batch_size', 1)
            grouped = [biz_batches[i:i + biz_batch_size] for i in range(0, len(biz_batches), biz_batch_size)]

            biz_sections_dict: Dict[str, Any] = {}
            mermaid_chunks: Dict[str, str] = {}
            for j, batch in enumerate(grouped):
                if len(batch) == 1:
                    section_key = f"biz_{batch[0].get('name', f'flow_{j}')}"
                else:
                    section_key = f"biz_batch_{j}"
                if section_key not in completed_biz_keys:
                    continue

                # 从 plan_sections.json 中查找对应内容 / Find matching content from plan_sections.json
                batch_entry: Dict[str, Any] = {"content": "", "mermaids": {}}
                for flow in batch:
                    flow_chunk_id = flow.get("chunk_id", f"flow_{j}")
                    for biz_sec in sections.get("biz_flows", []):
                        if biz_sec.get("chunk_id") == flow_chunk_id or biz_sec.get("key") == flow_chunk_id:
                            # 只取第一个匹配 flow 的 content（整批共享同一 content）
                            # Only take first matching flow's content (batch shares same content)
                            content = biz_sec.get("content", "")
                            if content and not batch_entry["content"]:
                                batch_entry["content"] = content
                            mermaid = biz_sec.get("mermaid", "")
                            if mermaid:
                                mermaid_chunks[flow_chunk_id] = mermaid
                                batch_entry["mermaids"][flow_chunk_id] = mermaid

                if batch_entry["content"]:
                    biz_sections_dict[section_key] = batch_entry

            if biz_sections_dict:
                plan_parts["biz_sections"] = biz_sections_dict
            if mermaid_chunks:
                plan_parts["mermaid_chunks"] = mermaid_chunks

        return plan_parts

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
            requirement_analysis=requirement_json,
            api_summary=api_summary_json,
            user_guidance=user_guidance or "(none)",
            reference_summary=reference_summary or "(none)",
            language=get_language_name(),
        )
        self.reset_steps()
        system_msg = render_prompt(
            PLAN_CHUNK_GLOBAL_SYSTEM,
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
        memory_dir: str = "",
    ) -> Dict[str, str]:
        """Phase B: 按 API group 逐个生成测试点 / Generate API test sections per group.

        使用 ProgressTracker 统一进度管理，已完成的 group (resume) 自动跳过。
        Uses ProgressTracker for unified progress; completed groups auto-skipped.
        """
        api_sections = plan_parts.get("api_sections", {})
        if isinstance(api_sections, str):
            api_sections = json.loads(api_sections)
            plan_parts["api_sections"] = api_sections
        if "api_sections" not in plan_parts:
            plan_parts["api_sections"] = api_sections

        # 构建 ProgressTracker — 从已完成的 section key 集合恢复
        # Build ProgressTracker — restore from completed section key set
        completed_ids = set(api_sections.keys()) if isinstance(api_sections, dict) else set()
        tracker = ProgressTracker.from_existing(
            total=len(api_groups), batch_size=1,
            completed_ids=completed_ids)

        all_items = [(g.get("chunk_id", f"api_{g.get('group_name', '')}"), g)
                     for g in api_groups]

        for batch_ids, batch_items, batch_idx, total_batches \
                in tracker.iter_batches(all_items):
            for group in batch_items:
                group_name = group.get("group_name", f"group_{batch_idx}")
                section_key = group.get("chunk_id", f"api_{group_name}")

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
                    global_context=global_context,
                    group_name=group_name,
                    test_focus=group.get("test_focus", ""),
                    group_api_ids=json.dumps(group_api_ids),
                    language=get_language_name(),
                )

                logger.info(
                    _("plan_gen.phase_b_chunk",
                      current=tracker.completed + 1, total=len(api_groups),
                      name=group_name, count=len(group_ifaces))
                )
                self.reset_steps()
                section_md = self.call_llm(prompt, system_with_context)
                api_sections[section_key] = section_md
                tracker.mark_completed(batch_ids)

            # 保存 chunk 进度（用 tracker 的轻量格式）/ Save with tracker lightweight format
            self._save_chunk_progress(
                memory_dir, plan_parts, api_groups=api_groups, api_tracker=tracker)

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
        memory_dir: str = "",
        api_groups: List[dict] = None,
    ) -> Dict[str, Dict[str, str]]:
        """Phase C: 按批次生成业务链路测试（Mermaid + 用例内容）。

        Generate biz flow test sections in batches (Mermaid + test content).
        使用 ProgressTracker 统一进度管理，已完成的批次 (resume) 自动跳过。
        Uses ProgressTracker for unified progress; completed batches auto-skipped.
        """
        biz_sections: Dict[str, Dict[str, str]] = plan_parts.get("biz_sections", {})
        if isinstance(biz_sections, str):
            biz_sections = json.loads(biz_sections)
            plan_parts["biz_sections"] = biz_sections
        if "biz_sections" not in plan_parts:
            plan_parts["biz_sections"] = biz_sections

        # 辅助：生成 batch key / Helper: generate batch key
        def _biz_batch_key(batch: List[dict], j: int) -> str:
            if not batch:
                return f"biz_batch_{j}"
            first_name = batch[0].get("name", f"flow_{j}")
            if len(batch) == 1:
                return f"biz_{first_name}"
            return f"biz_batch_{j}"

        # 构建 ProgressTracker — 从已完成的 section key 集合恢复
        # Build ProgressTracker — restore from completed section key set
        completed_ids = set(biz_sections.keys()) if isinstance(biz_sections, dict) else set()
        tracker = ProgressTracker.from_existing(
            total=len(biz_batches), batch_size=1,
            completed_ids=completed_ids)

        all_items = [(_biz_batch_key(batch, j), batch)
                     for j, batch in enumerate(biz_batches) if batch]

        for batch_ids, batch_items, batch_idx, total_batches \
                in tracker.iter_batches(all_items):
            for batch in batch_items:
                j = biz_batches.index(batch)
                section_key = _biz_batch_key(batch, j)
                first_name = batch[0].get("name", f"flow_{j}") if batch else f"flow_{j}"
                flow_names = first_name if len(batch) == 1 else \
                    ", ".join(f.get("name", "?") for f in batch)

                # ================================================================
                # Step 1: 逐流生成 Mermaid 图 / Per-flow Mermaid generation
                # ================================================================
                batch_mermaids: Dict[str, str] = {}
                for flow in batch:
                    chunk_id = flow.get("chunk_id", "")
                    mermaid_content = self._generate_mermaid_for_flow(
                        flow=flow,
                        iface_by_id=iface_by_id,
                        outline_json=outline_json,
                        global_context=global_context,
                        plan_parts=plan_parts,
                    )
                    batch_mermaids[chunk_id] = mermaid_content

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

                # ================================================================
                # Step 2: 生成 biz 用例内容（纯文本，不含 Mermaid）
                # Step 2: Generate biz test content (plain text, no Mermaid)
                # ================================================================
                prompt = render_prompt(
                    PLAN_CHUNK_BIZ_SECTION_USER,
                    interface_defs=json.dumps(batch_ifaces, ensure_ascii=False, indent=2),
                    user_guidance=user_guidance or "(none)",
                    language=get_language_name(),
                )

                system_with_context = render_prompt(
                    PLAN_CHUNK_BIZ_SECTION_SYSTEM,
                    global_context=global_context,
                    flows_list=flows_list,
                    language=get_language_name(),
                )

                # 日志：单 flow vs 批量 / Log: single vs batch
                if len(batch) == 1:
                    logger.info(
                        _("plan_gen.phase_c_chunk",
                          current=tracker.completed + 1, total=len(biz_batches), name=flow_names)
                    )
                else:
                    logger.info(
                        _("plan_gen.phase_c_batch",
                          current=tracker.completed + 1, total=len(biz_batches),
                          names=flow_names, count=len(batch))
                    )

                self.reset_steps()
                section_md = self.call_llm(prompt, system_with_context)

                # ================================================================
                # Step 3: 组装 batch entry — content 纯文本 + per-flow mermaid
                # Step 3: Build batch entry — plain text content + per-flow mermaid
                # ================================================================
                biz_sections[section_key] = {
                    "content": section_md,
                    "mermaids": batch_mermaids,
                }
                tracker.mark_completed(batch_ids)

            # 保存 chunk 进度（用 tracker 的轻量格式）/ Save with tracker lightweight format
            self._save_chunk_progress(
                memory_dir, plan_parts, api_groups=api_groups,
                biz_batches=biz_batches, biz_tracker=tracker)

        plan_parts["biz_sections"] = biz_sections
        return biz_sections

    def _save_sections_artifact(
        self,
        memory_dir: str,
        api_groups: List[dict],
        api_sections: Dict[str, str],
        biz_batches: List[List[dict]],
        biz_sections: Dict[str, Dict[str, str]],
        global_context: str,
    ):
        """保存分块结构到 plan_sections.json / Save section structure for revision.

        输出 schema 定义的三键结构：
        Outputs the three-key structure defined by the schema:
          {"business_understanding": ..., "single_api": [...], "biz_flows": [...]}
        content 为纯 markdown 文本，mermaid 独立存放。
        content is plain markdown text; mermaid is stored separately.
        """
        if not memory_dir:
            return

        from graph.nodes.helpers import save_pipeline_artifact

        single_api: List[dict] = []
        for group in api_groups:
            chunk_id = group.get("chunk_id", "")
            # 使用 chunk_id 作为查找键 / Use chunk_id as lookup key
            section_key = chunk_id or f"api_{group.get('group_name', '')}"
            content = api_sections.get(section_key, "")
            if content and content.strip():
                single_api.append({
                    "chunk_id": chunk_id if chunk_id else section_key,
                    "key": chunk_id if chunk_id else section_key,
                    "type": "api",
                    "name": group.get("group_name", ""),
                    "section": "single_api",
                    "content": content,
                    "api_ids": group.get("api_ids", []),
                    "test_focus": group.get("test_focus", ""),
                })

        biz_flows: List[dict] = []
        for j, batch in enumerate(biz_batches):
            if not batch:
                continue
            # 确定 section key / Determine section key
            if len(batch) == 1:
                section_key = f"biz_{batch[0].get('name', f'flow_{j}')}"
            else:
                section_key = f"biz_batch_{j}"

            entry = biz_sections.get(section_key, {})
            content = entry.get("content", "") if isinstance(entry, dict) else entry
            # per-flow mermaids: {chunk_id: mermaid_content}
            per_flow_mermaids = entry.get("mermaids", {}) if isinstance(entry, dict) else {}

            if content and content.strip():
                for flow in batch:
                    flow_chunk_id = flow.get("chunk_id", f"flow_{j}")
                    # 每个 flow 取自己的 mermaid / Each flow gets its own mermaid
                    flow_mermaid = per_flow_mermaids.get(flow_chunk_id, "")
                    biz_flows.append({
                        "chunk_id": flow_chunk_id,
                        "key": flow_chunk_id,
                        "type": "biz",
                        "name": flow.get("name", ""),
                        "section": "biz_flows",
                        "content": content,
                        "mermaid": flow_mermaid,
                        "involved_apis": flow.get("involved_apis", []),
                        "description": flow.get("description", ""),
                    })

        save_pipeline_artifact(memory_dir, "plan_sections.json", {
            "business_understanding": {
                "chunk_id": "business_understanding",
                "key": "business_understanding",
                "type": "global",
                "name": "Business Understanding",
                "content": global_context,
            },
            "single_api": single_api,
            "biz_flows": biz_flows,
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
    # 纯中文名可能产生仅有前缀的无效 chunk_id（如 "api_"），回退到默认值
    # Pure Chinese names may produce prefix-only chunk_id (e.g. "api_"); fall back to default
    if not safe or safe == prefix:
        safe = prefix + "chunk"
    return safe


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
