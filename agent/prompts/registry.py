"""PromptRegistry — 从 prompts/ 模块加载提示词。

Load and serve prompts from Python modules in the prompts/ directory.
"""

import logging
from typing import Any, Dict

from . import render_prompt  # noqa: F401 — re-exported for convenience

logger = logging.getLogger(__name__)


class PromptRegistry:
    """从 prompts/ 目录的 Python 模块加载提示词。

    Load agent prompts from Python modules. Each agent has:
      - system: str — system prompt template
      - user_template: str — user message template with {{var}} placeholders
    """

    def __init__(self):
        self._data: Dict[str, Dict[str, str]] = {}
        self._load()

    def _load(self):
        """从 prompts/ 模块导入所有提示词常量。

        Import all prompt constants from prompts/ modules.
        """
        from . import api_analyzer
        from . import case_generation
        from . import doc_parser
        from . import plan_generation
        from . import plan_parser as _plan_parser_mod
        from . import plan_reviser
        from . import requirement_analysis
        from . import skeleton_generation

        self._data = {
            "api_analyzer": {
                "system": api_analyzer.API_ANALYSIS_SYSTEM,
                "user_template": api_analyzer.API_ANALYSIS_USER,
            },
            "requirement_analyzer": {
                "system": requirement_analysis.REQUIREMENT_ANALYSIS_SYSTEM,
                "user_template": requirement_analysis.REQUIREMENT_ANALYSIS_USER,
            },
            "plan_generator": {
                "system": plan_generation.PLAN_GENERATION_SYSTEM,
                "user_template": plan_generation.PLAN_GENERATION_USER,
            },
            "plan_reviser": {
                "system": plan_reviser.PLAN_REVISER_SYSTEM,
                "user_template": plan_reviser.PLAN_REVISER_USER,
            },
            "plan_annotation_reviser": {
                "system": plan_reviser.PLAN_ANNOTATION_REVISER_SYSTEM,
                "user_template": plan_reviser.PLAN_ANNOTATION_REVISER_USER,
            },
            "plan_parser": {
                "system": _plan_parser_mod.PLAN_PARSER_SYSTEM,
                "user_template": _plan_parser_mod.PLAN_PARSER_USER,
            },
            "case_generator": {
                "system": case_generation.CASE_GENERATION_SYSTEM,
                "user_template": case_generation.CASE_GENERATION_USER,
            },
            "single_skeleton_generator": {
                "system": skeleton_generation.SINGLE_SKELETON_SYSTEM,
                "user_template": skeleton_generation.SINGLE_SKELETON_USER,
            },
            "biz_skeleton_generator": {
                "system": skeleton_generation.BIZ_SKELETON_SYSTEM,
                "user_template": skeleton_generation.BIZ_SKELETON_USER,
            },
            "doc_parser": {
                "system": doc_parser.DOC_PARSER_SYSTEM,
                "user_template": doc_parser.DOC_PARSER_USER,
            },
        }

    def get_system(self, agent_name: str) -> str:
        """返回 agent_name 的 system prompt。

        Return the system prompt for *agent_name*.
        """
        entry = self._data.get(agent_name)
        if entry is None:
            logger.warning("No prompt config for agent '%s'", agent_name)
            return ""
        return entry.get("system", "")

    def get_user_template(self, agent_name: str) -> str:
        """返回 agent_name 的 user_template。

        Return the user message template for *agent_name*.
        """
        entry = self._data.get(agent_name)
        if entry is None:
            return ""
        return entry.get("user_template", "")

    def build_user_message(self, agent_name: str, **kwargs) -> str:
        """渲染 user_template。Render the user_template for *agent_name* with kwargs."""
        template = self.get_user_template(agent_name)
        return render_prompt(template, **kwargs)

    def list_agents(self):
        """列出所有已配置的 agent 名称。Return names of all configured agents."""
        return list(self._data.keys())
