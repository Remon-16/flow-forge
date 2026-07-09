"""条件路由函数 — 决定 LangGraph 边的走向。

Edge/conditional routing functions for the LangGraph StateGraph.
"""

from graph.state import GraphState


def check_confirmed(state: GraphState) -> str:
    """human_confirm 之后的条件边。

    Conditional edge after human_confirm_node.
    Returns "confirmed" → parse_plan, "rejected" → revise_plan.
    """
    if state.get("plan_confirmed"):
        return "confirmed"
    return "rejected"


def route_after_api_confirm(state: GraphState) -> str:
    """analyze_api 之后的条件边。

    Conditional edge after analyze_api_node.
    Returns "next" → validate_urls, "loop" → re-analyze.
    """
    if state.get("api_summary_confirmed"):
        return "next"
    return "loop"
