"""需求分析节点 — 从需求文档中提取结构化信息。

analyze_requirement node: extracts structured info from requirement documents.
"""

import logging

from agents.requirement_analyzer import RequirementAnalyzer
from graph.state import GraphState

from .helpers import _settings, _knowledge, _sl, save_snapshot

logger = logging.getLogger(__name__)


def analyze_requirement_node(state: GraphState) -> GraphState:
    """运行需求分析器（单次 LLM 调用）。

    Run the requirement analyzer (single-shot LLM call).
    """
    state.setdefault("errors", [])

    text = state.get("requirement_text", "")
    if not text.strip():
        state["requirement_analysis"] = {
            "business_flows": [], "roles": [], "constraints": [], "exceptions": [],
        }
        return state

    print(f"\n[3/9] 分析需求文档...")
    print(f"  → RequirementAnalyzer 正在调用 LLM ({_settings.llm_model})...")
    if _sl():
        _sl().log_node_start("analyze_requirement", "3/9")

    agent = RequirementAnalyzer(_settings, _knowledge)
    result = agent.analyze(text)
    state["requirement_analysis"] = result

    memory_dir = state.get("memory_dir", "")
    if memory_dir:
        save_snapshot(memory_dir, "requirement_analysis.json", result)

    flows = len(result.get("business_flows", []))
    roles = len(result.get("roles", []))
    print(f"  → 提取 {flows} 个业务流程, {roles} 个角色")
    if _sl():
        _sl().log_node_end("analyze_requirement")

    return state
