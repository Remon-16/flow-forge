"""Main LangGraph StateGraph builder for the test-case generation pipeline."""

from __future__ import annotations

import logging

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from config.settings import Settings
from graph.nodes import (
    analyze_api_node,
    analyze_requirement_node,
    batch_controller_node,
    check_confirmed,
    configure,
    generate_cases_node,
    generate_plan_node,
    human_confirm_node,
    parse_docs_node,
    parse_plan_node,
    reload_interfaces_node,
    revise_plan_node,
    route_after_api_confirm,
    save_interfaces_node,
    validate_interface_urls_node,
    write_excel_node,
    write_output_node,
)
from graph.state import GraphState
from knowledge.search import KnowledgeSearch

logger = logging.getLogger(__name__)


def build_workflow(
    settings: Settings,
    knowledge: KnowledgeSearch | None = None,
    session_logger=None,
) -> StateGraph:
    """构建完整的测试用例生成 StateGraph。

    Build and compile the full test-case-generation StateGraph.

    Args:
        settings: 从 .env 加载的全局设置。Global settings loaded from .env.
        knowledge: 可选的知识库搜索。Created if enable_knowledge is on.
        session_logger: 可选的会话日志记录器。Optional SessionLogger.

    Returns:
        已编译的 StateGraph。A compiled StateGraph ready for ``.invoke()``.
    """
    if knowledge is None and settings.enable_knowledge:
        knowledge = KnowledgeSearch(settings.knowledge_dir)

    configure(settings, knowledge, session_logger)

    graph = StateGraph(GraphState)

    # --- Add nodes ---
    graph.add_node("parse_docs", parse_docs_node)
    graph.add_node("analyze_api", analyze_api_node)
    graph.add_node("validate_interface_urls", validate_interface_urls_node)
    graph.add_node("save_interfaces", save_interfaces_node)
    graph.add_node("analyze_requirement", analyze_requirement_node)
    graph.add_node("generate_plan", generate_plan_node)
    graph.add_node("human_confirm", human_confirm_node)
    graph.add_node("revise_plan", revise_plan_node)
    graph.add_node("reload_interfaces", reload_interfaces_node)
    graph.add_node("parse_plan", parse_plan_node)
    graph.add_node("batch_controller", batch_controller_node)
    graph.add_node("write_output", write_output_node)
    # Legacy nodes (non-batch mode)
    graph.add_node("generate_cases", generate_cases_node)
    graph.add_node("write_excel", write_excel_node)

    # --- Entry routing (supports resume mode) ---
    graph.add_node("entry", lambda s: s)
    graph.set_entry_point("entry")
    graph.add_conditional_edges(
        "entry",
        lambda s: "batch_controller" if s.get("resume") else "parse_docs",
        {"parse_docs": "parse_docs", "batch_controller": "batch_controller"},
    )

    # --- Edges ---
    graph.add_edge("parse_docs", "analyze_api")
    graph.add_conditional_edges("analyze_api", route_after_api_confirm, {
        "loop": "analyze_api",
        "next": "validate_interface_urls",
    })
    graph.add_edge("validate_interface_urls", "save_interfaces")
    graph.add_edge("save_interfaces", "analyze_requirement")
    graph.add_edge("analyze_requirement", "generate_plan")
    graph.add_edge("generate_plan", "human_confirm")
    graph.add_conditional_edges("human_confirm", check_confirmed, {
        "confirmed": "reload_interfaces",
        "rejected": "revise_plan",
    })
    graph.add_edge("revise_plan", "human_confirm")  # Feedback loop
    graph.add_edge("reload_interfaces", "parse_plan")
    graph.add_edge("parse_plan", "batch_controller")
    graph.add_edge("batch_controller", "write_output")
    graph.add_edge("write_output", END)

    return graph.compile(checkpointer=MemorySaver())
