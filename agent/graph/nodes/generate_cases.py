"""用例生成节点（旧版单次模式）。

Legacy single-shot case generation node — kept for backward compatibility.
"""

import logging

from agents.case_generator import CaseGenerator
from graph.state import GraphState

from .helpers import _settings, _knowledge, _sl, dicts_to_interfaces

logger = logging.getLogger(__name__)


def generate_cases_node(state: GraphState) -> GraphState:
    """从结构化计划 + 接口定义生成具体测试用例（旧版单次模式）。

    Generate concrete test cases from structured plan + interfaces (legacy).
    """
    state.setdefault("errors", [])

    agent = CaseGenerator(_settings, _knowledge)
    plan = state.get("plan_parsed")
    interfaces_raw = state.get("interfaces", [])
    user_guidance = state.get("user_guidance", "")

    print(f"\n[7/8] 生成测试用例...")
    print(f"  → CaseGenerator 正在调用 LLM ({_settings.llm_model})...")
    if _sl():
        _sl().log_node_start("generate_cases", "7/8")

    interfaces = dicts_to_interfaces(interfaces_raw)
    result = agent.generate(plan, interfaces, user_guidance=user_guidance)
    single_cases = result.get("single_cases", [])
    biz_flows = result.get("biz_flows", [])

    state["single_cases"] = single_cases
    state["biz_flows"] = biz_flows

    print(f"  → 生成 {len(single_cases)} 条单接口用例, {len(biz_flows)} 条业务链路")
    if _sl():
        _sl().log_node_end("generate_cases")

    return state
