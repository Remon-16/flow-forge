"""计划生成节点 — 基于需求分析和接口定义生成测试计划。

generate_plan node: generates test plan from requirement analysis + interfaces.
"""

import logging
from pathlib import Path

from agents.plan_generator import PlanGenerator
from graph.state import GraphState

from .helpers import _settings, _knowledge, _sl, summarize_reference_dir

logger = logging.getLogger(__name__)


def generate_plan_node(state: GraphState) -> GraphState:
    """生成测试计划 Markdown。

    Generate a test plan markdown from requirement analysis + interfaces.
    When reference_dir is set, operates in incremental update mode.
    """
    state.setdefault("errors", [])

    reference_dir = state.get("reference_dir", "")
    reference_summary = summarize_reference_dir(reference_dir)

    agent = PlanGenerator(_settings, _knowledge)

    analysis = state.get("requirement_analysis", {})
    interfaces = state.get("interfaces", [])
    api_summary = state.get("api_summary", [])
    user_guidance = state.get("user_guidance", "")

    if reference_dir:
        print(f"\n[4/9] 生成测试计划 (增量模式)...")
        print(f"  → 参考目录: {reference_dir}")
    else:
        print(f"\n[4/9] 生成测试计划...")
    print(f"  → PlanGenerator 正在调用 LLM ({_settings.llm_model})...")
    if _sl():
        _sl().log_node_start("generate_plan", "4/9")

    plan_md = agent.generate(
        analysis, interfaces,
        api_summary=api_summary,
        user_guidance=user_guidance,
        reference_summary=reference_summary,
    )
    state["plan_md"] = plan_md

    # Save plan.md
    memory_dir = state.get("memory_dir", "")
    if memory_dir:
        try:
            plan_path = Path(memory_dir) / "plan.md"
            plan_path.parent.mkdir(parents=True, exist_ok=True)
            plan_path.write_text(plan_md, encoding="utf-8")
        except Exception as e:
            logger.warning("Failed to save plan.md to memory_dir: %s", e)

    plan_len = len(plan_md)
    if _sl():
        plan_path = _sl().save_plan(plan_md)
        print(f"  → 计划已生成 ({plan_len} 字符)，已保存至 {plan_path}")
    else:
        print(f"  → 计划已生成 ({plan_len} 字符)")

    if _sl():
        _sl().log_node_end("generate_plan")

    return state
