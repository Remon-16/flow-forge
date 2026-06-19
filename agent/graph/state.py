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

    # === Output config ===
    output_dir: str             # Output root directory
    cases_dir: str              # Test case output subdirectory ({output_dir}/cases)
    memory_dir: str             # Agent output subdirectory ({output_dir}/memory)
    debug_snapshots: bool       # Save optional debug snapshots
    output_format: str          # "yaml" | "excel" | "both"
    batch_size: int             # Max cases per batch
    enable_validation: bool     # Whether to run case validation
    max_validation_retries: int # Max validation retries

    # === Document parsing ===
    requirement_text: str
    interfaces: List[Dict[str, Any]]
    api_raw_text: str          # Raw text of API doc (for --parse-mode raw)
    parse_mode: str            # "raw" | "rule" | "llm"
    parser_path: str           # Custom parser script path

    # === Requirement analysis ===
    requirement_analysis: Dict[str, Any]

    # === Plan generation ===
    plan_md: str
    plan_md_path: str
    plan_parsed: Any  # Structured TestPlan from parse_plan_node
    user_guidance: str  # User guidance from --prompt CLI flag

    # === API Analysis ===
    api_summary: List[Dict[str, Any]]
    api_summary_feedback: str
    api_summary_confirmed: bool

    # === Human review ===
    plan_confirmed: bool
    plan_feedback: str
    plan_feedback_type: str          # "text" | "annotations"
    plan_annotations: List[Dict[str, Any]]  # parsed plan_comments.json

    # === Case generation ===
    single_cases: List[Dict[str, Any]]
    biz_flows: List[Dict[str, Any]]

    # === Batch tracking ===
    batch_state: Dict[str, Any]          # Batch generation progress
    validation_failures: List[Dict]      # Cases that failed validation

    # === Resume & incremental ===
    resume: bool                         # Skip to batch generation from existing output_dir
    reference_dir: str                   # Reference directory for incremental updates

    # === Shared messages (ReAct agents use add_messages reducer) ===
    messages: Annotated[List, add_messages]

    # === Errors ===
    errors: List[str]
