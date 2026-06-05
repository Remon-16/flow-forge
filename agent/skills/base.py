"""Skill data class — a portable bundle of prompt extension + tools + constraints."""

from dataclasses import dataclass, field
from typing import List


@dataclass
class Skill:
    """An installable capability unit for agents.

    A Skill is a YAML-defined bundle that extends an agent's system prompt
    with additional instructions and optionally injects extra tools.

    Attributes:
        name: Unique skill identifier (e.g. ``sql_data_fetch``).
        description: Human-readable one-liner.
        version: Semver string.
        target_agents: Agent names this skill applies to (empty = all).
        prompt_extension: Additional instructions appended to the system prompt.
        tools: Tool names this skill depends on (injected automatically).
    """

    name: str
    description: str = ""
    version: str = "1.0"
    target_agents: List[str] = field(default_factory=list)
    prompt_extension: str = ""
    tools: List[str] = field(default_factory=list)
