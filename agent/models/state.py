"""Agent configuration models.

智能体配置数据模型。
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AgentConfig:
    """单个智能体的配置。

    Configuration for a single agent / subgraph.
    """

    name: str
    description: str = ""
    can_spawn_subagents: bool = False
    max_subagents: int = 3
    parent_agent: Optional[str] = None
