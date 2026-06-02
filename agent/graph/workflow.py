"""Main LangGraph StateGraph builder for the test-case generation pipeline."""

from __future__ import annotations

import logging

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from config.settings import Settings
from graph.nodes import (
    analyze_requirement_node,
    check_confirmed,
    configure,
    generate_cases_node,
    generate_plan_node,
    human_confirm_node,
    parse_docs_node,
    parse_plan_node,
    revise_plan_node,
    write_excel_node,
)
from graph.state import GraphState
from knowledge.rag import RAGKnowledgeBase
from prompts.registry import PromptRegistry

logger = logging.getLogger(__name__)


def build_workflow(
    settings: Settings,
    prompt_registry: PromptRegistry | None = None,
    rag: RAGKnowledgeBase | None = None,
) -> StateGraph:
    """Build and compile the full test-case-generation StateGraph.

    Args:
        settings: Global settings loaded from .env.
        prompt_registry: Optional PromptRegistry. Created from defaults if None.
        rag: Optional RAG knowledge base. Created and initialized if None.

    Returns:
        A compiled StateGraph ready for ``.invoke()``.
    """
    if prompt_registry is None:
        prompt_registry = PromptRegistry()
    if rag is None:
        rag = RAGKnowledgeBase(settings.knowledge_db_path)
        rag.initialize()

    configure(settings, prompt_registry, rag)

    graph = StateGraph(GraphState)

    # --- Add nodes ---
    graph.add_node("parse_docs", parse_docs_node)
    graph.add_node("analyze_requirement", analyze_requirement_node)
    graph.add_node("generate_plan", generate_plan_node)
    graph.add_node("human_confirm", human_confirm_node)
    graph.add_node("revise_plan", revise_plan_node)
    graph.add_node("parse_plan", parse_plan_node)
    graph.add_node("generate_cases", generate_cases_node)
    graph.add_node("write_excel", write_excel_node)

    # --- Edges ---
    graph.set_entry_point("parse_docs")
    graph.add_edge("parse_docs", "analyze_requirement")
    graph.add_edge("analyze_requirement", "generate_plan")
    graph.add_edge("generate_plan", "human_confirm")
    graph.add_conditional_edges("human_confirm", check_confirmed, {
        "confirmed": "parse_plan",
        "rejected": "revise_plan",
    })
    graph.add_edge("revise_plan", "human_confirm")  # Feedback loop
    graph.add_edge("parse_plan", "generate_cases")
    graph.add_edge("generate_cases", "write_excel")
    graph.add_edge("write_excel", END)

    return graph.compile(checkpointer=MemorySaver())
