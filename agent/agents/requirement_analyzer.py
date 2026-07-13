"""RequirementAnalyzer: extracts business flows, roles, constraints from text."""

import logging
from typing import Any, Dict, List, Optional

from .base import BaseAgent
from config.settings import Settings
from knowledge.search import KnowledgeSearch
from prompts import KNOWLEDGE_SECTION_HEADER
from prompts.requirement_analysis import (
    REQ_CHUNK_NOTICE,
    REQUIREMENT_ANALYSIS_SYSTEM,
    REQUIREMENT_ANALYSIS_USER,
)
from prompts.render import render_prompt
from i18n import get_language_name

logger = logging.getLogger(__name__)


class RequirementAnalyzer(BaseAgent):
    """Analyze requirement documents to extract structured test-relevant info."""

    def __init__(self, settings: Settings, knowledge: Optional[KnowledgeSearch] = None, skill_extensions: List[str] = None):
        super().__init__(
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            max_retries=settings.max_retries,
            max_steps=settings.max_steps,
            base_url=settings.llm_base_url,
            context_window=settings.llm_context_window,
            max_output_tokens=settings.llm_max_output_tokens,
            compression_threshold=settings.llm_context_compression_threshold,
            skill_extensions=skill_extensions,
        )
        self._knowledge = knowledge

    def analyze(self, requirement_text: str) -> Dict[str, Any]:
        """Analyze requirement text and return structured info.

        Uses token-aware chunking for long documents.  If the text fits within
        the context window, a single call is made.  Otherwise the text is
        split into chunks, each chunk is analyzed, and results are merged.

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

        input_tokens = self._estimate_input_tokens(
            REQUIREMENT_ANALYSIS_SYSTEM,
            render_prompt(REQUIREMENT_ANALYSIS_USER, requirement_text=requirement_text, language=get_language_name()),
        )

        if input_tokens < self._context_window * self._compression_threshold:
            # Single round — fits comfortably
            return self._analyze_single(requirement_text)

        logger.info(
            "Requirement text (%d chars, ~%d tokens) exceeds threshold, "
            "using multi-round chunking",
            len(requirement_text), input_tokens,
        )
        return self._process_long_text(
            text=requirement_text,
            system_msg=REQUIREMENT_ANALYSIS_SYSTEM,
            chunk_processor=self._analyze_chunk,
            result_merger=self._merge_analyses,
            chunk_notice=REQ_CHUNK_NOTICE,
        )

    def _analyze_single(self, requirement_text: str) -> Dict[str, Any]:
        """Single-round analysis for text that fits in context."""
        prompt = render_prompt(
            REQUIREMENT_ANALYSIS_USER,
            requirement_text=requirement_text,
            language=get_language_name(),
        )

        if self._knowledge is not None:
            docs = self._knowledge.search(requirement_text[:2000], n_results=3)
            if docs:
                knowledge_context = "\n---\n".join(docs)
                prompt += f"\n\n{KNOWLEDGE_SECTION_HEADER}{knowledge_context}"

        logger.info("Analyzing requirement document (%d chars)...", len(requirement_text))
        result = self.call_llm_json(prompt, REQUIREMENT_ANALYSIS_SYSTEM)
        return self._normalize_result(result)

    def _analyze_chunk(self, chunk: str, _accumulated: str) -> Dict[str, Any]:
        """Process a single chunk of the requirement text."""
        prompt = render_prompt(
            REQUIREMENT_ANALYSIS_USER,
            requirement_text=chunk,
            language=get_language_name(),
        )
        return self.call_llm_json(prompt, REQUIREMENT_ANALYSIS_SYSTEM)

    @staticmethod
    def _merge_analyses(results: list, _system_msg: str) -> Dict[str, Any]:
        """Merge results from multiple chunks into a single analysis."""
        merged: Dict[str, Any] = {
            "business_flows": [],
            "roles": [],
            "constraints": [],
            "exceptions": [],
        }
        seen = {k: set() for k in merged}
        for r in results:
            if isinstance(r, dict):
                for key in merged:
                    items = r.get(key, [])
                    if isinstance(items, list):
                        for item in items:
                            item_str = str(item)
                            if item_str not in seen[key]:
                                seen[key].add(item_str)
                                merged[key].append(item)
        logger.info(
            "Merged analysis: %d flows, %d roles, %d constraints, %d exceptions",
            len(merged["business_flows"]), len(merged["roles"]),
            len(merged["constraints"]), len(merged["exceptions"]),
        )
        return merged

    @staticmethod
    def _normalize_result(result: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure expected keys exist."""
        for key in ("business_flows", "roles", "constraints", "exceptions"):
            if key not in result:
                result[key] = []
        return result
