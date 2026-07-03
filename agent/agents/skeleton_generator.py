"""骨架生成器：为单接口用例和业务链路用例生成测试用例骨架。
Skeleton generators: produce test case skeletons for single and biz flow cases.
"""

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from .base import BaseAgent
from config.settings import Settings, get_strategy
from knowledge.search import KnowledgeSearch
from prompts import KNOWLEDGE_SECTION_HEADER
from prompts.skeleton_generation import (
    SINGLE_SKELETON_SYSTEM,
    SINGLE_SKELETON_USER,
    BIZ_SKELETON_SYSTEM,
    BIZ_SKELETON_USER,
    URL_CORRECTION_SYSTEM,
    URL_CORRECTION_USER,
)
from prompts.render import render_prompt
from i18n import _, get_language_name

logger = logging.getLogger(__name__)


# ============================================================================
# 模块级辅助函数 / Module-level helper functions
# ============================================================================

def _serialize_plan_single(plan) -> str:
    """序列化单接口测试点 / Serialize single test points from plan for prompt."""
    parts = []
    if hasattr(plan, "business_summary") and plan.business_summary:
        parts.append(f"## Business Understanding\n{plan.business_summary}")
    if hasattr(plan, "single_test_points") and plan.single_test_points:
        parts.append("\n## Single API Test Points")
        for api_id, points in plan.single_test_points.items():
            parts.append(f"\n### {api_id}")
            for p in points:
                parts.append(
                    f"- [{p.tag}] {p.test_id}: {p.description} ({p.scenario_type})"
                )
    return "\n".join(parts)


def _serialize_plan_biz(plan) -> str:
    """序列化业务链路场景 / Serialize biz flow scenarios from plan for prompt."""
    parts = []
    if hasattr(plan, "business_summary") and plan.business_summary:
        parts.append(f"## Business Understanding\n{plan.business_summary}")
    if hasattr(plan, "biz_flow_scenarios") and plan.biz_flow_scenarios:
        parts.append("\n## Business Flow Scenarios")
        for scenario in plan.biz_flow_scenarios:
            parts.append(
                f"- {scenario.get('name', '')}: {scenario.get('description', '')}"
            )
    if hasattr(plan, "mermaid_flows") and plan.mermaid_flows:
        parts.append("\n## Business Flow Diagrams")
        for name, diagram in plan.mermaid_flows.items():
            parts.append(f"\n### {name}\n```mermaid\n{diagram}\n```")
    return "\n".join(parts)


def _serialize_partial_single(batch_grouped: dict, plan) -> str:
    """序列化单批测试点（仅含本批 API 和测试点）。
    Serialize a subset of test points for one batch.

    Args:
        batch_grouped: {api_id: [PlanStep, ...]} — 本批测试点子集 / subset of test points.
        plan: 完整 TestPlan（用于获取 business_summary）/ Full TestPlan for business_summary.
    """
    parts = []
    # 业务理解摘要（如有）/ Business understanding summary (if available)
    if hasattr(plan, "business_summary") and plan.business_summary:
        parts.append(f"## Business Understanding\n{plan.business_summary}")
    parts.append("\n## Single API Test Points")
    for api_id, points in batch_grouped.items():
        parts.append(f"\n### {api_id}")
        for p in points:
            parts.append(
                f"- [{p.tag}] {p.test_id}: {p.description} ({p.scenario_type})"
            )
    return "\n".join(parts)


def _make_partial_biz_plan(plan, batch_scenarios: List[Dict]) -> Any:
    """为业务链路分批构造局部 plan 对象。
    Build a partial plan object for biz flow batching.

    包含 business_summary + 部分 biz_flow_scenarios + mermaid_flows。
    Contains business_summary + partial biz_flow_scenarios + mermaid_flows.
    """
    partial = type("_PartialPlan", (), {})()
    if hasattr(plan, "business_summary"):
        partial.business_summary = plan.business_summary
    partial.biz_flow_scenarios = batch_scenarios
    if hasattr(plan, "mermaid_flows"):
        partial.mermaid_flows = plan.mermaid_flows
    else:
        partial.mermaid_flows = {}
    return partial


def _normalize_interfaces(items: List[Any]) -> List[Dict[str, Any]]:
    """将 InterfaceDef/dict 统一转为 dict 列表。
    Convert mixed InterfaceDef/dicts to unified list of dicts.
    """
    result = []
    for item in items:
        if isinstance(item, dict):
            result.append({
                "test_id": item.get("test_id", ""),
                "api_name": item.get("api_name", item.get("name", "")),
                "app_name": item.get("app_name", item.get("app", "")),
                "method": item.get("method", "GET"),
                "url": item.get("url", ""),
            })
        elif hasattr(item, "test_id"):
            result.append({
                "test_id": item.test_id,
                "api_name": item.api_name,
                "app_name": item.app_name,
                "method": item.method,
                "url": item.url,
            })
    return result


def _count_validate(
    agent: "BaseAgent",
    prompt: str,
    system_msg: str,
    json_key: str,
    expected_count: int,
    label: str,
    strategy: str = "fail",
) -> List[Dict]:
    """调用 LLM 并校验返回数量，按策略处理不匹配。
    Call LLM, extract list from JSON, validate count with configurable strategy.

    Args:
        agent: BaseAgent 实例（用于 call_llm_json）/ BaseAgent instance.
        prompt: 用户 prompt / User prompt.
        system_msg: 系统 prompt / System prompt.
        json_key: 从结果 dict 中提取的 JSON key / JSON key to extract from result dict.
        expected_count: 预期数量 / Expected number of items.
        label: 日志标签 / Human-readable label for log messages.
        strategy: "fail"（抛异常）/ "warn"（警告继续）/ "skip"（跳过校验）。

    Returns:
        从 JSON 响应中提取的列表 / List of items from the JSON response.

    Raises:
        ValueError: 仅当 strategy 为 "fail" 且所有重试耗尽时。
    """
    items = []
    agent.reset_steps()  # 每批重置步数计数器 / Reset step counter per batch
    for attempt in range(agent._max_retries + 1):
        result = agent.call_llm_json(prompt, system_msg)
        items = result.get(json_key, [])
        if len(items) == expected_count:
            logger.info(_("skel_gen.batch_progress", count=len(items), label=label))
            return items
        logger.warning(
            _("skel_gen.count_mismatch", label=label,
              attempt=attempt + 1, total=agent._max_retries + 1,
              expected=expected_count, actual=len(items)),
        )

    last_count = len(items)
    # 跳过校验 / Skip validation
    if strategy == "skip":
        logger.info(_("skel_gen.count_check_skipped", label=label, count=last_count))
        return items
    # 警告但继续 / Warn but continue
    elif strategy == "warn":
        logger.warning(
            _("skel_gen.count_mismatch_final", label=label,
              retries=agent._max_retries + 1, expected=expected_count, actual=last_count),
        )
        return items
    # 严格模式：抛异常 / Strict mode: raise error
    else:
        raise ValueError(
            f"{label} count validation failed after {agent._max_retries + 1} "
            f"attempts: expected {expected_count}, got {last_count}"
        )


# ============================================================================
# BaseSkeletonGenerator — 骨架生成器基类
# Base class for skeleton generators
# ============================================================================

class _BaseSkeletonGenerator(BaseAgent):
    """骨架生成器基类，提供 _build_prompt 等共享方法。
    Base class for skeleton generators with shared prompt-building logic.
    """

    def _build_prompt(
        self,
        plan_str: str,
        iface_dicts: List[Dict],
        api_summary,
        user_guidance: str,
        user_template: str,
        system_msg: str,
        batch_notice: str = "",
        knowledge_query: str = "test case skeleton",
    ) -> str:
        """构建骨架生成 prompt / Build skeleton generation prompt.

        包含模板渲染、知识注入、token 上限检查。
        Includes template rendering, knowledge injection, and token limit check.

        Args:
            plan_str: 序列化的测试计划文本 / Serialized test plan text.
            iface_dicts: 规范化后的接口定义列表 / Normalized interface definitions.
            api_summary: API 分析摘要 / API analysis summary.
            user_guidance: 用户附加指引 / User additional guidance.
            user_template: 用户 prompt 模板 / User prompt template.
            system_msg: 系统 prompt（用于 token 估算）/ System prompt (for token estimation).
            batch_notice: 批次提示前缀 / Batch notice prefix (e.g. "[Batch 1/4] ").
            knowledge_query: 知识库搜索关键词 / Knowledge base search query.

        Returns:
            完整的 prompt 字符串 / Complete prompt string.
        """
        # 渲染 prompt 模板 / Render prompt template
        api_summary_str = json.dumps(api_summary or [], ensure_ascii=False, indent=2)
        prompt = render_prompt(
            user_template,
            test_plan=plan_str,
            interface_defs=json.dumps(iface_dicts, ensure_ascii=False, indent=2),
            api_summary=api_summary_str,
            user_guidance=user_guidance or "(none)",
            language=get_language_name(),
        )

        # 附加批次提示 / Prepend batch notice
        if batch_notice:
            prompt = batch_notice + prompt

        # 注入知识库片段 / Inject knowledge base snippets
        if self._knowledge is not None:
            docs = self._knowledge.search(knowledge_query, n_results=3)
            if docs:
                prompt += f"\n\n{KNOWLEDGE_SECTION_HEADER}" + "\n---\n".join(docs)

        # token 上限检查 / Token limit check
        input_tokens = self._estimate_input_tokens(system_msg, prompt)
        if input_tokens > self._context_window:
            raise ValueError(
                f"Skeleton generation input exceeds context window: "
                f"{input_tokens} / {self._context_window} tokens"
            )
        return prompt


# ============================================================================
# SingleSkeletonGenerator
# ============================================================================

class SingleSkeletonGenerator(_BaseSkeletonGenerator):
    """生成单接口测试用例骨架 / Generate single API test case skeletons.

    支持分批：当测试点数超过 skeleton_batch_size 时自动拆分为多批。
    Supports batching: auto-splits when test points exceed skeleton_batch_size.
    """

    def __init__(
        self,
        settings: Settings,
        knowledge: Optional[KnowledgeSearch] = None,
        skill_extensions: List[str] = None,
    ):
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
        # 骨架分批大小 / Skeleton batch size
        self._skeleton_batch_size = getattr(settings, "skeleton_batch_size", 30)
        # 校验规则列表 / Validation rules list
        self._validation_rules = getattr(settings, "validation_rules", [])

    # ------------------------------------------------------------------
    # 公共入口 / Public entry point
    # ------------------------------------------------------------------

    def generate(
        self,
        plan,
        interfaces: List[Any],
        api_summary: Optional[List[Dict]] = None,
        user_guidance: str = "",
    ) -> List[Dict]:
        """生成单接口用例骨架 / Generate single API case skeletons.

        测试点 ≤ batch_size 时单次调用，超过则分批处理。
        Single call when test points ≤ batch_size, batch mode otherwise.
        """
        # 计算预期用例总数 / Calculate expected skeleton count
        expected_count = (
            sum(len(points) for points in plan.single_test_points.values())
            if hasattr(plan, "single_test_points") and plan.single_test_points
            else 0
        )
        if expected_count == 0:
            logger.info(_("skel_gen.no_single_points"))
            return []

        iface_dicts = _normalize_interfaces(interfaces)

        if expected_count <= self._skeleton_batch_size:
            return self._generate_single_batch(
                plan, iface_dicts, api_summary, user_guidance, expected_count,
            )
        else:
            return self._generate_multi_batch(
                plan, iface_dicts, api_summary, user_guidance, expected_count,
            )

    # ------------------------------------------------------------------
    # 单批生成 / Single batch generation
    # ------------------------------------------------------------------

    def _generate_single_batch(
        self, plan, iface_dicts, api_summary, user_guidance, expected_count,
    ) -> List[Dict]:
        """一次性生成全部骨架 / Generate all skeletons in one LLM call."""
        plan_str = _serialize_plan_single(plan)
        prompt = self._build_prompt(
            plan_str, iface_dicts, api_summary, user_guidance,
            SINGLE_SKELETON_USER, SINGLE_SKELETON_SYSTEM,
        )
        return _count_validate(
            self, prompt,
            render_prompt(SINGLE_SKELETON_SYSTEM, language=get_language_name()),
            "single_skeletons", expected_count,
            "single case skeletons",
            get_strategy(self._validation_rules, "skeleton_count"),
        )

    # ------------------------------------------------------------------
    # 分批生成 / Multi-batch generation
    # ------------------------------------------------------------------

    def _generate_multi_batch(
        self, plan, iface_dicts, api_summary, user_guidance, expected_count,
    ) -> List[Dict]:
        """分批生成骨架，每批 ≤ batch_size 个测试点 / Generate skeletons in batches."""
        # 1. 将所有测试点 flatten 为 (api_id, point) 列表
        #    Flatten all test points into [(api_id, point), ...]
        all_points: List[Tuple[str, Any]] = []
        for api_id, points in plan.single_test_points.items():
            for p in points:
                all_points.append((api_id, p))

        # 2. 按 batch_size 切片，每片重新按 api_id 分组
        #    Slice by batch_size, regroup each slice by api_id
        batches: List[Dict[str, List]] = []
        for i in range(0, len(all_points), self._skeleton_batch_size):
            batch_points = all_points[i:i + self._skeleton_batch_size]
            grouped: Dict[str, List] = {}
            for api_id, p in batch_points:
                grouped.setdefault(api_id, []).append(p)
            batches.append(grouped)

        logger.info(
            _("skel_gen.generating_single_batches",
              count=expected_count, batches=len(batches), size=self._skeleton_batch_size),
        )

        # 3. 逐批调用 LLM / Call LLM for each batch
        all_skeletons: List[Dict] = []
        strategy = get_strategy(self._validation_rules, "skeleton_count")
        for i, batch_grouped in enumerate(batches):
            batch_expected = sum(len(pts) for pts in batch_grouped.values())
            label = f"single batch {i+1}/{len(batches)}"

            batch_plan_str = _serialize_partial_single(batch_grouped, plan)
            batch_prompt = self._build_prompt(
                batch_plan_str, iface_dicts, api_summary, user_guidance,
                SINGLE_SKELETON_USER, SINGLE_SKELETON_SYSTEM,
                batch_notice=f"[Batch {i+1}/{len(batches)}] ",
            )

            skeletons = _count_validate(
                self, batch_prompt,
                render_prompt(SINGLE_SKELETON_SYSTEM, language=get_language_name()),
                "single_skeletons", batch_expected, label, strategy,
            )
            all_skeletons.extend(skeletons)

        # 4. 最终汇总校验 / Final total count check
        if len(all_skeletons) != expected_count:
            logger.warning(
                _("skel_gen.total_count_mismatch",
                  type="single", expected=expected_count, actual=len(all_skeletons)),
            )

        logger.info(
            _("skel_gen.single_result",
              count=len(all_skeletons), batches=len(batches)),
        )
        return all_skeletons

    # ------------------------------------------------------------------
    # URL 修正 / URL correction
    # ------------------------------------------------------------------

    def correct_urls(
        self,
        bad_cases: List[Dict],
        interfaces: List[Any],
        api_doc_text: str,
        api_summary: Optional[List[Dict]] = None,
    ) -> List[Dict]:
        """使用可信接口 + API 文档预搜索修正 URL。
        Correct URLs using trusted interfaces + API doc pre-search.

        Interfaces are assumed to have passed source validation
        (validate_interface_urls_node + user review + reload).
        """
        iface_dicts = _normalize_interfaces(interfaces)

        # 构建每个 bad case 的搜索片段 / Build search snippets per bad case
        snippets_parts = []
        for case in bad_cases:
            relevance_id = case.get("relevance_id", "")
            bad_url = case.get("url", "")
            api_name = case.get("api_name", "")
            http_method = case.get("method", "GET")

            # 从可信接口中查找正确 URL / Look up correct URL from trusted interfaces
            correct_iface = None
            for iface in iface_dicts:
                if iface.get("test_id") == relevance_id:
                    correct_iface = iface
                    break

            if correct_iface:
                correct_url = correct_iface.get("url", "")
                snippet = self._fuzzy_search_api_doc(
                    url=correct_url, http_method=http_method,
                    api_doc_text=api_doc_text, max_snippet_tokens=2000,
                )
            else:
                # 模糊匹配接口，然后搜索 / Fuzzy match in interfaces, then search
                matched = self._fuzzy_match_interface(
                    url=bad_url, api_name=api_name,
                    http_method=http_method, interfaces=iface_dicts,
                )
                if matched:
                    snippet = self._fuzzy_search_api_doc(
                        url=matched.get("url", ""), http_method=http_method,
                        api_doc_text=api_doc_text, max_snippet_tokens=2000,
                    )
                else:
                    snippet = self._fuzzy_search_api_doc(
                        url=bad_url, http_method=http_method,
                        api_doc_text=api_doc_text, max_snippet_tokens=2000,
                    )

            snippets_parts.append(
                f"### Case: {case.get('test_id', '?')}\n"
                f"Current URL: {bad_url}\n"
                f"Relevant API doc:\n{snippet}"
            )

        prompt = URL_CORRECTION_USER.replace(
            "{{bad_cases}}",
            json.dumps(bad_cases, ensure_ascii=False, indent=2),
        ).replace(
            "{{api_doc_text}}", "\n---\n".join(snippets_parts)
        ).replace(
            "{{interface_defs}}",
            json.dumps(iface_dicts, ensure_ascii=False, indent=2),
        )

        logger.info(_("skel_gen.correcting_urls", count=len(bad_cases)))
        expected_count = len(bad_cases)

        # URL 修正对数量偏差容忍度更高，使用 warn 策略
        # URL correction is more tolerant of count mismatch
        strategy = get_strategy(self._validation_rules, "url_check")

        for attempt in range(self._max_retries + 1):
            result = self.call_llm_json(prompt, URL_CORRECTION_SYSTEM)
            corrected = result.get("cases") or result.get("single_skeletons") or []
            if not corrected:
                if isinstance(result, list):
                    corrected = result
            if not corrected:
                logger.warning(
                    _("skel_gen.url_correction_empty",
                      type="single", attempt=attempt + 1, total=self._max_retries + 1),
                )
                continue
            if len(corrected) == expected_count:
                return corrected
            logger.warning(
                _("skel_gen.url_correction_count_mismatch",
                  type="single", attempt=attempt + 1, total=self._max_retries + 1,
                  expected=expected_count, actual=len(corrected)),
            )

        # 按策略处理 / Handle by strategy
        if strategy == "fail":
            raise ValueError(
                f"URL correction count validation failed after "
                f"{self._max_retries + 1} attempts"
            )
        # warn 或 skip：回退到原始 bad_cases / fallback to original
        logger.warning(
            _("skel_gen.url_correction_fallback",
              type="single", retries=self._max_retries + 1),
        )
        return bad_cases


# ============================================================================
# BizSkeletonGenerator
# ============================================================================

class BizSkeletonGenerator(_BaseSkeletonGenerator):
    """生成业务链路测试用例骨架 / Generate business flow test case skeletons.

    支持分批：当场景数超过 skeleton_batch_size 时自动拆分为多批。
    Supports batching: auto-splits when scenarios exceed skeleton_batch_size.
    """

    def __init__(
        self,
        settings: Settings,
        knowledge: Optional[KnowledgeSearch] = None,
        skill_extensions: List[str] = None,
    ):
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
        # 骨架分批大小 / Skeleton batch size
        self._skeleton_batch_size = getattr(settings, "skeleton_batch_size", 30)
        # 校验规则列表 / Validation rules list
        self._validation_rules = getattr(settings, "validation_rules", [])

    # ------------------------------------------------------------------
    # 公共入口 / Public entry point
    # ------------------------------------------------------------------

    def generate(
        self,
        plan,
        interfaces: List[Any],
        api_summary: Optional[List[Dict]] = None,
        user_guidance: str = "",
    ) -> List[Dict]:
        """生成业务链路用例骨架 / Generate biz flow case skeletons.

        场景数 ≤ batch_size 时单次调用，超过则分批处理。
        Single call when scenarios ≤ batch_size, batch mode otherwise.
        """
        # 跳过：无业务链路场景 / Skip: no biz flow scenarios
        if not (hasattr(plan, "biz_flow_scenarios") and plan.biz_flow_scenarios):
            logger.info(_("skel_gen.no_biz_scenarios"))
            return []

        iface_dicts = _normalize_interfaces(interfaces)
        expected_count = len(plan.biz_flow_scenarios)

        if expected_count <= self._skeleton_batch_size:
            return self._generate_single_batch(
                plan, iface_dicts, api_summary, user_guidance, expected_count,
            )
        else:
            return self._generate_multi_batch(
                plan, iface_dicts, api_summary, user_guidance, expected_count,
            )

    # ------------------------------------------------------------------
    # 单批生成 / Single batch generation
    # ------------------------------------------------------------------

    def _generate_single_batch(
        self, plan, iface_dicts, api_summary, user_guidance, expected_count,
    ) -> List[Dict]:
        """一次性生成全部业务链路骨架 / Generate all biz skeletons in one LLM call."""
        plan_str = _serialize_plan_biz(plan)
        prompt = self._build_prompt(
            plan_str, iface_dicts, api_summary, user_guidance,
            BIZ_SKELETON_USER, BIZ_SKELETON_SYSTEM,
            knowledge_query="business flow test case",
        )
        return _count_validate(
            self, prompt,
            render_prompt(BIZ_SKELETON_SYSTEM, language=get_language_name()),
            "biz_skeletons", expected_count,
            "biz flow skeletons",
            get_strategy(self._validation_rules, "skeleton_count"),
        )

    # ------------------------------------------------------------------
    # 分批生成 / Multi-batch generation
    # ------------------------------------------------------------------

    def _generate_multi_batch(
        self, plan, iface_dicts, api_summary, user_guidance, expected_count,
    ) -> List[Dict]:
        """分批生成业务链路骨架 / Generate biz skeletons in batches."""
        scenarios = plan.biz_flow_scenarios
        total_batches = (len(scenarios) + self._skeleton_batch_size - 1) // self._skeleton_batch_size

        logger.info(
            _("skel_gen.generating_biz_batches",
              count=expected_count, batches=total_batches, size=self._skeleton_batch_size),
        )

        all_skeletons: List[Dict] = []
        strategy = get_strategy(self._validation_rules, "skeleton_count")
        for i in range(0, len(scenarios), self._skeleton_batch_size):
            batch_scenarios = scenarios[i:i + self._skeleton_batch_size]
            batch_idx = i // self._skeleton_batch_size + 1
            batch_expected = len(batch_scenarios)
            label = f"biz batch {batch_idx}/{total_batches}"

            # 构造局部 plan / Build partial plan
            batch_plan = _make_partial_biz_plan(plan, batch_scenarios)
            batch_plan_str = _serialize_plan_biz(batch_plan)
            batch_prompt = self._build_prompt(
                batch_plan_str, iface_dicts, api_summary, user_guidance,
                BIZ_SKELETON_USER, BIZ_SKELETON_SYSTEM,
                batch_notice=f"[Batch {batch_idx}/{total_batches}] ",
                knowledge_query="business flow test case",
            )

            skeletons = _count_validate(
                self, batch_prompt,
                render_prompt(BIZ_SKELETON_SYSTEM, language=get_language_name()),
                "biz_skeletons", batch_expected, label, strategy,
            )
            all_skeletons.extend(skeletons)

        # 最终汇总校验 / Final total count check
        if len(all_skeletons) != expected_count:
            logger.warning(
                _("skel_gen.total_count_mismatch",
                  type="biz", expected=expected_count, actual=len(all_skeletons)),
            )

        logger.info(
            _("skel_gen.batch_progress", count=len(all_skeletons),
              label=f"biz flow skeletons"),
        )
        return all_skeletons

    # ------------------------------------------------------------------
    # URL 修正 / URL correction
    # ------------------------------------------------------------------

    def correct_urls(
        self,
        bad_cases: List[Dict],
        interfaces: List[Any],
        api_doc_text: str,
        api_summary: Optional[List[Dict]] = None,
    ) -> List[Dict]:
        """使用可信接口 + API 文档预搜索修正业务链路 URL。
        Correct biz flow URLs using trusted interfaces + API doc pre-search.
        """
        iface_dicts = _normalize_interfaces(interfaces)

        # 构建每个步骤的搜索片段 / Build search snippets per step
        snippets_parts = []
        for case in bad_cases:
            steps = case.get("steps", [])
            for step in steps:
                relevance_id = step.get("relevance_id", "")
                bad_url = step.get("url", "")
                api_name = step.get("api_name", "")
                http_method = step.get("method", "GET")

                correct_iface = None
                for iface in iface_dicts:
                    if iface.get("test_id") == relevance_id:
                        correct_iface = iface
                        break

                if correct_iface:
                    correct_url = correct_iface.get("url", "")
                    snippet = self._fuzzy_search_api_doc(
                        url=correct_url, http_method=http_method,
                        api_doc_text=api_doc_text, max_snippet_tokens=2000,
                    )
                else:
                    matched = self._fuzzy_match_interface(
                        url=bad_url, api_name=api_name,
                        http_method=http_method, interfaces=iface_dicts,
                    )
                    if matched:
                        snippet = self._fuzzy_search_api_doc(
                            url=matched.get("url", ""), http_method=http_method,
                            api_doc_text=api_doc_text, max_snippet_tokens=2000,
                        )
                    else:
                        snippet = self._fuzzy_search_api_doc(
                            url=bad_url, http_method=http_method,
                            api_doc_text=api_doc_text, max_snippet_tokens=2000,
                        )

                snippets_parts.append(
                    f"### Step: {step.get('step_id', '?')}\n"
                    f"Current URL: {bad_url}\n"
                    f"Relevant API doc:\n{snippet}"
                )

        prompt = URL_CORRECTION_USER.replace(
            "{{bad_cases}}",
            json.dumps(bad_cases, ensure_ascii=False, indent=2),
        ).replace(
            "{{api_doc_text}}", "\n---\n".join(snippets_parts)
        ).replace(
            "{{interface_defs}}",
            json.dumps(iface_dicts, ensure_ascii=False, indent=2),
        )

        logger.info(_("skel_gen.correcting_biz_urls", count=len(bad_cases)))
        expected_count = len(bad_cases)
        strategy = get_strategy(self._validation_rules, "url_check")

        for attempt in range(self._max_retries + 1):
            result = self.call_llm_json(prompt, URL_CORRECTION_SYSTEM)
            corrected = (
                result.get("cases")
                or result.get("biz_skeletons")
                or result.get("biz_flows")
                or []
            )
            if not corrected:
                if isinstance(result, list):
                    corrected = result
            if not corrected:
                logger.warning(
                    _("skel_gen.url_correction_empty",
                      type="biz", attempt=attempt + 1, total=self._max_retries + 1),
                )
                continue
            if len(corrected) == expected_count:
                return corrected
            logger.warning(
                _("skel_gen.url_correction_count_mismatch",
                  type="biz", attempt=attempt + 1, total=self._max_retries + 1,
                  expected=expected_count, actual=len(corrected)),
            )

        # 按策略处理 / Handle by strategy
        if strategy == "fail":
            raise ValueError(
                f"Biz URL correction count validation failed after "
                f"{self._max_retries + 1} attempts"
            )
        # warn 或 skip：回退到原始 bad_cases / fallback to original
        logger.warning(
            _("skel_gen.url_correction_fallback",
              type="biz", retries=self._max_retries + 1),
        )
        return bad_cases
