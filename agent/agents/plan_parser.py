"""PlanParser: parse plan_sections.json into structured TestPlan.

从 plan_sections.json（非 plan.md）解析测试计划为结构化 TestPlan。
支持 token 感知的贪心切分：整体 → case_type 拆分 → 贪心分批。
Parses plan_sections.json (not plan.md) into structured TestPlan.
Supports token-aware greedy chunking: whole → case_type split → greedy.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from .base import BaseAgent
from config.settings import Settings, get_strategy, get_flow_match_failure_action
from models.schema import (
    InterfaceDef,
    PlanStep,
    TestPlan,
)
from i18n import _

logger = logging.getLogger(__name__)


class PlanParser(BaseAgent):
    """Parse plan_sections.json into structured TestPlan."""

    def __init__(self, settings: Settings, skill_extensions: List[str] = None):
        super().__init__(
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            temperature=0.1,
            max_retries=settings.max_retries,
            max_steps=settings.max_steps,
            base_url=settings.llm_base_url,
            context_window=settings.llm_context_window,
            max_output_tokens=settings.llm_max_output_tokens,
            compression_threshold=settings.llm_context_compression_threshold,
            skill_extensions=skill_extensions,
        )
        # 存储设置，供关联校验等场景使用 / Store settings for association check etc.
        self._settings = settings

    # ========================================================================
    # 主入口 / Main entry point
    # ========================================================================

    def parse_from_sections(
        self, sections: dict, interfaces: Optional[List[Dict[str, Any]]] = None,
    ) -> TestPlan:
        """从 plan_sections.json 结构解析为 TestPlan。

        Token 感知贪心切分：
        Token-aware greedy chunking:
          1. 整体尝试 → 若不超过窗口阈值，一次 LLM 调用
          2. 超过 → 按 case_type 拆分 (single_api / biz_flows)
          3. 仍超过 → 贪心算法逐 section 累加
        """
        bu = sections.get("business_understanding", "")
        # 兼容新旧格式 / Compatible with old (str) and new (dict) format
        if isinstance(bu, dict):
            business_summary = bu.get("content", "")
        else:
            business_summary = bu
        single_api = sections.get("single_api", [])
        biz_flows = sections.get("biz_flows", [])
        # 保存原始 biz_flows 供关联校验重试使用
        # Store original biz_flows for flow association retries
        self._original_biz_sections = biz_flows

        from prompts.plan_parser import PLAN_PARSER_SYSTEM as system_msg
        # 估算 system prompt tokens / Estimate system prompt tokens
        system_tokens = self._token_counter.count(system_msg)
        # 输出窗口约束 / Output window constraint
        # 公式从 (context_window - system_tokens - 200) * 阈值
        # 改为   (max_output_tokens - system_tokens - 200) * 阈值
        # 基于 input ≈ output 假设，输入窗口不会小于输出窗口。
        # 原输入窗口约束几乎不触发（128K >> 测试计划），但输出截断实际已发生。
        # Formula changed from (context_window - system_tokens - 200) * threshold
        # to (max_output_tokens - system_tokens - 200) * threshold.
        # Based on input ≈ output assumption; input window won't exceed output window.
        chunk_overhead = 200
        threshold = 0.9
        max_chunk_tokens = int(
            (self._max_output_tokens - system_tokens - chunk_overhead) * threshold
        )

        # 组装完整 prompt 文本 / Build full prompt text
        full_text = self._assemble_parse_text(business_summary, single_api, biz_flows)
        full_tokens = self._estimate_section_tokens(system_msg, full_text)

        if full_tokens <= max_chunk_tokens:
            # 整体一次解析 / Parse all at once
            result = self._parse_single_batch(full_text, system_msg, interfaces)
        else:
            # 按 case_type 拆分 / Split by case_type
            logger.info(
                "Plan too large (%d > %d tokens), splitting by case_type",
                full_tokens, max_chunk_tokens,
            )
            result = self._parse_with_greedy_chunking(
                business_summary, single_api, biz_flows,
                system_msg, max_chunk_tokens, interfaces,
            )

        # 构建 TestPlan / Build TestPlan
        plan = self._build_testplan(result)
        plan.business_summary = business_summary

        # 从 sections 填充 mermaid_flows / Populate mermaid_flows from sections
        # key 为 flow name（匹配 _make_partial_biz_plan 的按名称过滤逻辑）
        # key is flow name (matching _make_partial_biz_plan's name-based filtering)
        # 值保持原样（含 ```mermaid 包裹），下游只加 heading 不再重复包裹
        # value kept as-is (with ```mermaid wrapper); downstream only adds heading
        for biz_sec in biz_flows:
            name = biz_sec.get("name", "")
            mermaid = biz_sec.get("mermaid", "")
            if name and mermaid:
                plan.mermaid_flows[name] = mermaid

        # Fallback interfaces
        if not plan.api_definitions and interfaces:
            plan.api_definitions = [
                InterfaceDef(
                    test_id=iface.get("test_id", ""),
                    api_name=iface.get("api_name", ""),
                    app_name=iface.get("app_name", ""),
                    method=iface.get("method", "GET"),
                    url=iface.get("url", ""),
                )
                for iface in interfaces
            ]

        # Mermaid 关联校验 / Mermaid flow association check
        # 在解析完成后检查 biz_flow_scenarios 与 mermaid_flows 的关联性。
        # After parsing completes, check association between biz_flow_scenarios
        # and mermaid_flows.
        if plan.biz_flow_scenarios and plan.mermaid_flows:
            plan = self._validate_flow_association(plan)

        return plan

    # ========================================================================
    # 贪心切分 / Greedy chunking
    # ========================================================================

    def _parse_with_greedy_chunking(
        self,
        business_summary: str,
        single_api: List[dict],
        biz_flows: List[dict],
        system_msg: str,
        max_chunk_tokens: int,
        interfaces: Optional[List[Dict[str, Any]]],
    ) -> dict:
        """贪心切分解析 / Greedy chunking parse.

        1. 先尝试 single_api 整体 / Try single_api as a whole
        2. 再尝试 biz_flows 整体 / Try biz_flows as a whole
        3. 任一块超过 → 贪心逐 section 累加 / Either over → greedy per-section
        """
        merged: dict = {
            "api_definitions": [],
            "single_test_points": {},
            "biz_flow_scenarios": [],
        }

        # Single API 部分 / Single API section
        single_text = self._assemble_parse_text("", single_api, [])
        single_tokens = self._estimate_section_tokens(system_msg, single_text)
        if single_tokens <= max_chunk_tokens:
            if single_api:
                r = self._parse_single_batch(single_text, system_msg, interfaces)
                self._merge_into(merged, r)
        else:
            # 贪心切分 single_api / Greedy chunk single_api
            logger.info("single_api too large (%d > %d), greedy chunking", single_tokens, max_chunk_tokens)
            for batch_text in self._greedy_batch_sections(single_api, system_msg, max_chunk_tokens):
                r = self._parse_single_batch(batch_text, system_msg, interfaces)
                self._merge_into(merged, r)

        # Biz flows 部分 / Biz flows section
        biz_text = self._assemble_parse_text("", [], biz_flows)
        biz_tokens = self._estimate_section_tokens(system_msg, biz_text)
        if biz_tokens <= max_chunk_tokens:
            if biz_flows:
                r = self._parse_single_batch(biz_text, system_msg, interfaces)
                self._merge_into(merged, r)
        else:
            logger.info("biz_flows too large (%d > %d), greedy chunking", biz_tokens, max_chunk_tokens)
            for batch_text in self._greedy_batch_sections(biz_flows, system_msg, max_chunk_tokens):
                r = self._parse_single_batch(batch_text, system_msg, interfaces)
                self._merge_into(merged, r)

        return merged

    def _greedy_batch_sections(
        self, sections: List[dict], system_msg: str, max_chunk_tokens: int,
    ):
        """贪心算法将 sections 分批 / Greedy batch sections within token budget.

        依次加入 section，直到累计 token 接近 max_chunk_tokens，
        然后产出当前 batch 并开始新 batch。
        Add sections one by one until approaching max_chunk_tokens,
        then yield the current batch and start a new one.
        """
        batch: List[dict] = []
        batch_tokens = 0

        for sec in sections:
            # 估算该 section 的 prompt token / Estimate this section's prompt tokens
            sec_text = self._section_to_text(sec)
            sec_tokens = self._estimate_section_tokens(system_msg, sec_text)

            if batch and batch_tokens + sec_tokens > max_chunk_tokens:
                # 当前 batch 已满，产出 / Current batch full, yield it
                yield self._assemble_parse_text("",
                    [s for s in batch if s.get("section") == "single_api"],
                    [s for s in batch if s.get("section") == "biz_flows"],
                )
                batch = []
                batch_tokens = 0

            batch.append(sec)
            batch_tokens += sec_tokens

        # 产出最后一个 batch / Yield the last batch
        if batch:
            yield self._assemble_parse_text("",
                [s for s in batch if s.get("section") == "single_api"],
                [s for s in batch if s.get("section") == "biz_flows"],
            )

    # ========================================================================
    # 流程图关联校验 / Mermaid flow association check
    # ========================================================================

    def _validate_flow_association(self, plan: TestPlan) -> TestPlan:
        """校验 biz_flow_scenarios 与 mermaid_flows 的关联性。

        Validate association between biz_flow_scenarios and mermaid_flows.

        按 parse_plan_validation 配置的策略（fail/warn/skip）处理失配场景。
        Handle unmatched scenarios per configured strategy (fail/warn/skip).
        """
        from utils.flow_matcher import match_mermaids_to_scenarios
        from prompts.plan_parser import PLAN_PARSER_SYSTEM as system_msg

        # 读取校验配置 / Read validation config
        rules = getattr(self._settings, "parse_plan_validation_rules", [])
        strategy = get_strategy(rules, "flow_match", default="warn")
        max_retries = getattr(
            self._settings, "parse_plan_validation_max_retries", 3,
        )
        enabled = getattr(
            self._settings, "parse_plan_validation_enabled", True,
        )

        # 开关关闭 → 等同 skip / Disabled → equivalent to skip
        if not enabled:
            strategy = "skip"

        if strategy == "skip":
            logger.info(
                _("plan_parser.flow_match_skipped",
                  total=len(plan.biz_flow_scenarios)),
            )
            return plan

        # 获取原始 biz_sections（用于重试）/ Get original biz_sections for retry
        original_biz = getattr(self, "_original_biz_sections", [])

        all_scenarios = list(plan.biz_flow_scenarios)
        mermaid_flows = plan.mermaid_flows
        final_exhausted = False

        for attempt in range(max_retries + 1):
            matched, orphaned = match_mermaids_to_scenarios(
                all_scenarios, mermaid_flows,
            )
            if not orphaned:
                # 全部匹配成功 / All matched successfully
                plan.biz_flow_scenarios = matched
                return plan

            if attempt < max_retries:
                names_str = ", ".join(orphaned)
                logger.warning(
                    _("plan_parser.flow_match_retry",
                      attempt=attempt + 1, max_retries=max_retries,
                      count=len(orphaned), names=names_str),
                )
                # 只重新解析失配的场景 / Re-parse only orphaned scenarios
                orphaned_sections = [
                    s for s in original_biz
                    if s.get("name", "") in orphaned
                ]
                if orphaned_sections:
                    retry_text = self._assemble_parse_text(
                        "", [], orphaned_sections,
                    )
                    try:
                        new_result = self._parse_single_batch(
                            retry_text, system_msg, None,
                        )
                        # 保留已匹配的场景，追加重新解析的结果
                        # Keep matched scenarios, append re-parsed results
                        new_scenarios = new_result.get(
                            "biz_flow_scenarios", [],
                        )
                        all_scenarios = matched + new_scenarios
                    except Exception as e:
                        logger.warning(
                            "Flow match retry %d failed: %s",
                            attempt + 1, e,
                        )
                else:
                    # 无原始 section 可重试，标记耗尽 / No section to retry, mark exhausted
                    final_exhausted = True
                    break
            else:
                final_exhausted = True
                break

        # 重试耗尽后的处理 / Handle retries exhausted
        if final_exhausted or attempt >= max_retries:
            orphaned_list = ", ".join(orphaned)
            if strategy == "fail":
                logger.error(
                    _("plan_parser.flow_match_failed",
                      count=len(orphaned), names=orphaned_list),
                )
                raise ValueError(
                    f"Flow association failed after {max_retries} "
                    f"retries: orphaned scenarios: {orphaned_list}"
                )
            else:
                # warn 策略：按 failure_action 处理
                # Warn strategy: handle by failure_action
                failure_action = get_flow_match_failure_action(
                    rules, default="discard",
                )
                if failure_action == "keep":
                    logger.warning(
                        _("plan_parser.flow_match_orphaned",
                          count=len(orphaned), names=orphaned_list,
                          action="keep"),
                    )
                    # 保留所有场景，包括失配的 / Keep all scenarios
                    plan.biz_flow_scenarios = all_scenarios
                else:
                    # discard（默认）：丢弃失配场景
                    # discard (default): drop orphaned scenarios
                    logger.warning(
                        _("plan_parser.flow_match_orphaned",
                          count=len(orphaned), names=orphaned_list,
                          action="discard"),
                    )
                    plan.biz_flow_scenarios = matched

        return plan

    # ========================================================================
    # 辅助 / Helpers
    # ========================================================================

    def _assemble_parse_text(
        self, business_summary: str, single_api: List[dict], biz_flows: List[dict],
    ) -> str:
        """将 sections 组装为 LLM prompt 文本 / Assemble sections into LLM prompt text."""
        parts = []
        if business_summary and business_summary.strip():
            parts.append(business_summary.strip())
        for sec in single_api:
            content = sec.get("content", "")
            if content and content.strip():
                parts.append(content.strip())
        for sec in biz_flows:
            content = sec.get("content", "")
            mermaid = sec.get("mermaid", "")
            combined = []
            if mermaid and mermaid.strip():
                combined.append(mermaid.strip())
            if content and content.strip():
                combined.append(content.strip())
            if combined:
                parts.append("\n\n".join(combined))
        return "\n\n".join(parts)

    def _section_to_text(self, sec: dict) -> str:
        """单个 section 转文本 / Single section to text."""
        content = sec.get("content", "")
        mermaid = sec.get("mermaid", "")
        if mermaid and mermaid.strip():
            return mermaid.strip() + "\n\n" + content
        return content

    def _estimate_section_tokens(self, system_msg: str, text: str) -> int:
        """估算 section 文本的 input tokens / Estimate input tokens for section text."""
        from prompts.plan_parser import PLAN_PARSER_USER
        from prompts.render import render_prompt
        prompt = render_prompt(PLAN_PARSER_USER, plan_md=text)
        return self._estimate_input_tokens(system_msg, prompt)

    def _parse_single_batch(
        self, text: str, system_msg: str,
        interfaces: Optional[List[Dict[str, Any]]],
    ) -> dict:
        """单批次 LLM 调用 / Single batch LLM call."""
        from prompts.plan_parser import PLAN_PARSER_USER
        from prompts.render import render_prompt
        prompt = render_prompt(PLAN_PARSER_USER, plan_md=text)
        try:
            return self.call_llm_json_object(prompt, system_msg, "api_definitions")
        except Exception as e:
            logger.warning("LLM plan parsing failed: %s", e)
            return {"api_definitions": [], "single_test_points": {}, "biz_flow_scenarios": []}

    @staticmethod
    def _merge_into(target: dict, source: dict):
        """将 source 结果合并到 target / Merge source result into target."""
        seen_api = {(ad.get("test_id"), ad.get("url")) for ad in target.get("api_definitions", [])}
        for ad in source.get("api_definitions", []):
            key = (ad.get("test_id", ""), ad.get("url", ""))
            if key not in seen_api:
                seen_api.add(key)
                target.setdefault("api_definitions", []).append(ad)
        for api_id, points in source.get("single_test_points", {}).items():
            if api_id not in target.setdefault("single_test_points", {}):
                target["single_test_points"][api_id] = []
            seen_tps = {tp.get("test_id") for tp in target["single_test_points"][api_id]}
            for tp in points:
                if tp.get("test_id") not in seen_tps:
                    target["single_test_points"][api_id].append(tp)
        for scenario in source.get("biz_flow_scenarios", []):
            target.setdefault("biz_flow_scenarios", []).append(scenario)

    # ========================================================================
    # 结果构建（保留） / Result construction (kept)
    # ========================================================================

    def _build_testplan(self, result: dict) -> TestPlan:
        """将解析结果构建为 TestPlan / Build TestPlan from parsed result."""
        api_defs = []
        for ad in result.get("api_definitions", []):
            api_defs.append(InterfaceDef(
                test_id=ad.get("test_id", ""),
                api_name=ad.get("api_name", ""),
                app_name=ad.get("app_name", ""),
                method=ad.get("method", "GET"),
                url=ad.get("url", ""),
            ))

        test_points: Dict[str, List[PlanStep]] = {}
        for api_id, points in result.get("single_test_points", {}).items():
            steps = []
            for p in points:
                steps.append(PlanStep(
                    test_id=p.get("test_id", ""),
                    description=p.get("description", ""),
                    tag=p.get("tag", "P1"),
                    scenario_type=p.get("scenario_type", "positive"),
                ))
            test_points[api_id] = steps

        return TestPlan(
            api_definitions=api_defs,
            single_test_points=test_points,
            biz_flow_scenarios=result.get("biz_flow_scenarios", []),
        )

    # ========================================================================
    # 已删除方法（旧 plan.md 解析路径）
    # Removed methods (old plan.md parsing path):
    #   parse(plan_md), _llm_parse(), _parse_chunk_processor(),
    #   _regex_parse(), _extract_section(), _extract_mermaid()
    # 这些方法从 plan.md 文本中提取数据，已被 plan_sections.json 输入替代。
    # These extracted data from plan.md text; replaced by plan_sections.json input.
    # ========================================================================
