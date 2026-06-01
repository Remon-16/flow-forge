"""PipelineState — tracks progress and artifacts through the pipeline."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PipelineState:
    """Holds all intermediate data and status through the generation pipeline."""

    # Phase tracking
    phase: str = "init"  # init, plan_generated, plan_confirmed, cases_generated
    converged: bool = False

    # Inputs
    requirement_paths: List[str] = field(default_factory=list)
    api_path: str = ""

    # Raw parsed content
    requirement_text: str = ""
    interfaces: list = field(default_factory=list)

    # Phase 1 outputs
    requirement_analysis: Dict[str, Any] = field(default_factory=dict)
    plan_md: str = ""
    plan_md_path: str = ""

    # Phase 2 outputs
    single_cases: list = field(default_factory=list)
    biz_flows: list = field(default_factory=list)
    excel_path: str = ""

    # Error tracking
    errors: List[str] = field(default_factory=list)

    def add_error(self, error: str) -> None:
        self.errors.append(error)
