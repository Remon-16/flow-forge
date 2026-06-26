"""Main LangGraph StateGraph builder for the test-case generation pipeline."""

from __future__ import annotations

import json
import logging
from pathlib import Path

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

# 阶段名到下一节点的映射 / Stage name to next node mapping
STAGE_TO_NEXT_NODE = {
    "": "parse_docs",
    "parse_docs": "analyze_api",
    "analyze_api": "validate_interface_urls",
    "validate_urls": "save_interfaces",
    "save_interfaces": "analyze_requirement",
    "analyze_requirement": "generate_plan",
    "generate_plan": "human_confirm",
    "human_confirm": "reload_interfaces",
    "reload_interfaces": "parse_plan",
    "parse_plan": "batch_controller",
    "batch_controller": "write_output",
    "write_output": "write_output",
}


def _route_resume(state: GraphState) -> str:
    """根据 pipeline_state.json 决定从哪个节点恢复。

    Reads the pipeline progress marker to determine the next node.
    Falls back to batch_controller (legacy resume) if no marker found.
    """
    memory_dir = state.get("memory_dir", "")
    if not memory_dir:
        return "batch_controller"

    state_path = Path(memory_dir) / "pipeline_state.json"
    if not state_path.exists():
        return "batch_controller"

    try:
        with open(state_path, "r", encoding="utf-8") as f:
            ps = json.load(f)
    except Exception:
        logger.warning("Failed to read pipeline_state.json, falling back to batch_controller")
        return "batch_controller"

    stage = ps.get("completed_stage", "")
    next_node = STAGE_TO_NEXT_NODE.get(stage, "parse_docs")
    logger.info("Resume: stage=%s → next_node=%s", stage, next_node)
    return next_node


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

    # --- Entry routing (supports full-pipeline resume mode) ---
    graph.add_node("entry", lambda s: s)
    graph.set_entry_point("entry")
    graph.add_conditional_edges(
        "entry",
        lambda s: _route_resume(s) if s.get("resume") else "parse_docs",
        {
            "parse_docs": "parse_docs",
            "analyze_api": "analyze_api",
            "validate_interface_urls": "validate_interface_urls",
            "save_interfaces": "save_interfaces",
            "analyze_requirement": "analyze_requirement",
            "generate_plan": "generate_plan",
            "human_confirm": "human_confirm",
            "reload_interfaces": "reload_interfaces",
            "parse_plan": "parse_plan",
            "batch_controller": "batch_controller",
            "write_output": "write_output",
        },
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
