"""SkillRegistry — discover, load and inject Skills for agents."""

import logging
from pathlib import Path
from typing import Dict, List

import yaml

from .base import Skill

logger = logging.getLogger(__name__)


class SkillRegistry:
    """Loads YAML skill definitions from ``skills/builtin/`` and ``skills/custom/``
    and provides them to agent builders.

    Each Skill is a portable bundle containing:
      - ``prompt_extension`` — appended to the agent's system prompt
      - ``tools`` — tool names the skill depends on
      - ``target_agents`` — which agents should receive this skill
    """

    def __init__(self, skills_dir: str = "", flat: bool = False):
        if not skills_dir:
            skills_dir = str(Path(__file__).resolve().parent)
        self._skills: Dict[str, Skill] = {}
        if flat:
            self._load_all(Path(skills_dir))
        else:
            self._load_all(Path(skills_dir) / "builtin")
            self._load_all(Path(skills_dir) / "custom")

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------
    def _load_all(self, directory: Path):
        if not directory.exists():
            logger.debug("Skill directory not found: %s", directory)
            return
        for yaml_file in directory.glob("*.yaml"):
            try:
                with open(yaml_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                if not data.get("name"):
                    logger.warning("Skipping skill file without 'name': %s", yaml_file)
                    continue
                skill = Skill(
                    name=data["name"],
                    description=data.get("description", ""),
                    version=data.get("version", "1.0"),
                    target_agents=data.get("target_agents", []),
                    prompt_extension=data.get("prompt_extension", ""),
                    tools=data.get("tools", []),
                )
                self._skills[skill.name] = skill
                logger.debug("Loaded skill: %s (v%s)", skill.name, skill.version)
            except Exception:
                logger.exception("Failed to load skill from %s", yaml_file)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------
    def get_for_agent(self, agent_name: str) -> List[Skill]:
        """Return all skills applicable to *agent_name*."""
        return [
            s
            for s in self._skills.values()
            if not s.target_agents or agent_name in s.target_agents
        ]

    def build_system_prompt(self, agent_name: str, base_prompt: str) -> str:
        """Augment *base_prompt* with prompt_extensions from applicable skills."""
        skills = self.get_for_agent(agent_name)
        if not skills:
            return base_prompt
        extensions = [s.prompt_extension for s in skills if s.prompt_extension]
        if not extensions:
            return base_prompt
        return base_prompt + "\n\n" + "\n\n".join(extensions)

    def get_tool_names(self, agent_name: str) -> List[str]:
        """Collect tool names from all skills applicable to *agent_name*."""
        names: List[str] = []
        for s in self.get_for_agent(agent_name):
            names.extend(s.tools)
        return list(dict.fromkeys(names))  # dedup, preserve order

    def list_skills(self) -> List[str]:
        return sorted(self._skills.keys())
