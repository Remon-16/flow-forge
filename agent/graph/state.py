"""LangGraph global state TypedDict — passed between nodes in the main workflow."""

from typing import Any, Dict, List, TypedDict

from langgraph.graph.message import add_messages
from typing_extensions import Annotated


class GraphState(TypedDict, total=False):
    """State carried through the test-case-generation pipeline.

    Each key is written by one node and read by downstream nodes.
    """

    # === Input ===
    requirement_paths: List[str]
    api_path: str
    output_path: str
    plan_only: bool

    # === Document parsing ===
    requirement_text: str
    interfaces: List[Dict[str, Any]]

    # === Requirement analysis ===
    requirement_analysis: Dict[str, Any]

    # === Plan generation ===
    plan_md: str
    plan_md_path: str

    # === API Analysis ===
    api_summary: List[Dict[str, Any]]
    api_summary_feedback: str
    api_summary_confirmed: bool

    # === Human review ===
    plan_confirmed: bool
    plan_feedback: str

    # === Case generation ===
    single_cases: List[Dict[str, Any]]
    biz_flows: List[Dict[str, Any]]

    # === Shared messages (ReAct agents use add_messages reducer) ===
    messages: Annotated[List, add_messages]

    # === Errors ===
    errors: List[str]
