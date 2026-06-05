"""Agent configuration and ReAct termination config."""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class ReActTerminationConfig:
    """Multi-layer termination conditions for ReAct loops.

    Every value can be set per-agent in ``config/prompts.yaml``.
    """

    # Layer 1 — hard limits (prevents infinite loops)
    max_iterations: int = 10
    max_tool_calls_total: int = 20
    max_time_seconds: int = 120

    # Layer 2 — token budget (prevents token explosion)
    max_input_tokens: int = 16000
    max_output_tokens_per_call: int = 4096

    # Layer 3 — no-progress detection (prevents thrashing)
    max_consecutive_same_tool: int = 3
    max_consecutive_no_result_change: int = 3
    tool_result_similarity_threshold: float = 0.95

    # Layer 4 — quality threshold
    min_improvement_ratio: float = 0.0

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ReActTerminationConfig":
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in valid_keys})


@dataclass
class AgentConfig:
    """Configuration for a single ReAct agent / subgraph."""

    name: str
    description: str = ""
    can_spawn_subagents: bool = False
    max_subagents: int = 3
    parent_agent: Optional[str] = None
