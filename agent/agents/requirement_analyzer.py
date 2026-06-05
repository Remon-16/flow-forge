"""RequirementAnalyzer: extracts business flows, roles, constraints from text."""

import logging
from typing import Any, Dict, Optional

from .base import BaseAgent
from config.settings import Settings
from knowledge.search import KnowledgeSearch
from prompts.requirement_analysis import (
    REQUIREMENT_ANALYSIS_SYSTEM,
    REQUIREMENT_ANALYSIS_USER,
)
from prompts.render import render_prompt

logger = logging.getLogger(__name__)


class RequirementAnalyzer(BaseAgent):
    """Analyze requirement documents to extract structured test-relevant info."""

    def __init__(self, settings: Settings, knowledge: Optional[KnowledgeSearch] = None):
        super().__init__(
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            max_retries=settings.max_retries,
            max_steps=settings.max_steps,
            base_url=settings.llm_base_url,
        )
        self._knowledge = knowledge

    def analyze(self, requirement_text: str) -> Dict[str, Any]:
        """Analyze requirement text and return structured info.

        Returns dict with keys:
            business_flows, roles, constraints, exceptions
        """
        if not requirement_text.strip():
            logger.warning("Empty requirement text, returning empty analysis")
            return {
                "business_flows": [],
                "roles": [],
                "constraints": [],
                "exceptions": [],
            }

        prompt = render_prompt(
            REQUIREMENT_ANALYSIS_USER,
            requirement_text=requirement_text[:8000],
        )

        # Conditionally append knowledge context
        if self._knowledge is not None:
            docs = self._knowledge.search(requirement_text, n_results=3)
            if docs:
                knowledge_context = "\n---\n".join(docs)
                prompt += f"\n\n## 知识库参考\n{knowledge_context}"

        logger.info("Analyzing requirement document (%d chars)...", len(requirement_text))
        result = self.call_llm_json(prompt, REQUIREMENT_ANALYSIS_SYSTEM)

        # Ensure expected keys exist
        for key in ("business_flows", "roles", "constraints", "exceptions"):
            if key not in result:
                result[key] = []

        logger.info(
            "Extracted %d flows, %d roles, %d constraints, %d exceptions",
            len(result["business_flows"]),
            len(result["roles"]),
            len(result["constraints"]),
            len(result["exceptions"]),
        )
        return result
