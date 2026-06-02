"""PromptRegistry: load and serve prompts from config/prompts.yaml."""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from .render import render_prompt

logger = logging.getLogger(__name__)


class PromptRegistry:
    """Load agent prompts and termination configs from a YAML file.

    Each agent has:
      - system:  str  — system prompt template
      - user_template: str — user message template with {{var}} placeholders
      - termination: dict (optional) — ReAct termination overrides
    """

    def __init__(self, yaml_path: Optional[str] = None):
        if yaml_path is None:
            yaml_path = str(Path(__file__).resolve().parent.parent / "config" / "prompts.yaml")
        self._path = Path(yaml_path)
        self._data: Dict[str, Any] = {}
        self._base_react_rules: str = ""
        self._default_termination: Dict[str, Any] = {}
        self._load()

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------
    def _load(self):
        if not self._path.exists():
            raise FileNotFoundError(f"prompts.yaml not found at {self._path}")
        with open(self._path, "r", encoding="utf-8") as f:
            self._data = yaml.safe_load(f) or {}

        self._base_react_rules = self._data.pop("_base_react_rules", None) or {}
        self._default_termination = self._data.pop("_default_termination", None) or {}

    # ------------------------------------------------------------------
    # System prompt (base + _base_react_rules auto-appended)
    # ------------------------------------------------------------------
    def get_system(self, agent_name: str) -> str:
        """Return the system prompt for *agent_name*.

        The global ``_base_react_rules`` YAML anchor is automatically
        appended to every system prompt.
        """
        entry = self._data.get(agent_name)
        if entry is None:
            logger.warning("No prompt config for agent '%s'", agent_name)
            return ""
        system = entry.get("system", "")
        if self._base_react_rules:
            rules_text = yaml.dump(self._base_react_rules, allow_unicode=True, default_flow_style=False)
            system += "\n\n## 行为约束\n" + rules_text
        return system

    def get_user_template(self, agent_name: str) -> str:
        entry = self._data.get(agent_name)
        if entry is None:
            return ""
        return entry.get("user_template", "")

    def get_termination(self, agent_name: str) -> Dict[str, Any]:
        """Return termination config merged with defaults.

        Per-agent values override defaults; missing keys fall back to
        ``_default_termination``.
        """
        entry = self._data.get(agent_name)
        per_agent = (entry or {}).get("termination") or {}
        merged = dict(self._default_termination)
        merged.update(per_agent)
        return merged

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------
    def build_user_message(self, agent_name: str, **kwargs) -> str:
        """Render the user_template for *agent_name* with the given kwargs."""
        template = self.get_user_template(agent_name)
        return render_prompt(template, **kwargs)

    def list_agents(self):
        """Return names of all configured agents (excluding internal keys)."""
        return [k for k in self._data if not k.startswith("_")]
