"""ApiAnalyzer: analyze API docs for completeness and generate structured summaries."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from .base import BaseAgent
from config.settings import Settings
from prompts.api_analyzer import (
    API_ANALYSIS_REVISE_SYSTEM,
    API_ANALYSIS_REVISE_USER,
    API_ANALYSIS_SYSTEM,
    API_ANALYSIS_USER,
)
from prompts.render import render_prompt
from i18n import get_language_name

logger = logging.getLogger(__name__)


class ApiAnalyzer(BaseAgent):
    """Analyze API documentation and produce structured summaries.

    Identifies: description, auth requirements, parameter patterns, uncertainties.
    Supports revision based on user feedback.
    Supports both structured interfaces (rule/llm modes) and raw text (raw mode).
    """

    def __init__(self, settings: Settings, skill_extensions: List[str] = None):
        super().__init__(
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            temperature=0.3,
            max_retries=settings.max_retries,
            max_steps=settings.max_steps,
            base_url=settings.llm_base_url,
            context_window=settings.llm_context_window,
            max_output_tokens=settings.llm_max_output_tokens,
            compression_threshold=settings.llm_context_compression_threshold,
            skill_extensions=skill_extensions,
        )
        self._settings = settings

    def analyze(self, interfaces: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Generate API summary for the given structured interfaces.

        Returns list of dicts with keys:
            api_path, method, description, need_token, auth_type,
            request_summary, response_summary, notes, uncertainties
        """
        iface_json = json.dumps(interfaces, ensure_ascii=False, indent=2)
        prompt = render_prompt(
            API_ANALYSIS_USER,
            interfaces=iface_json,
            extra_context="",
            language=get_language_name(),
        )

        logger.info("Analyzing %d interfaces...", len(interfaces))
        system_msg = render_prompt(API_ANALYSIS_SYSTEM, language=get_language_name())
        result = self.call_llm_json(prompt, system_msg)
        return self._normalize_result(result)

    def revise(
        self,
        interfaces: List[Dict[str, Any]],
        current_summary: List[Dict[str, Any]],
        feedback: str,
    ) -> List[Dict[str, Any]]:
        """Revise the API summary based on user feedback."""

        iface_json = json.dumps(interfaces, ensure_ascii=False, indent=2)
        summary_json = json.dumps(current_summary, ensure_ascii=False, indent=2)

        prompt = render_prompt(
            API_ANALYSIS_REVISE_USER,
            current_summary=summary_json,
            interfaces=iface_json,
            feedback=feedback,
        )

        logger.info("Revising API summary based on feedback...")
        result = self.call_llm_json(prompt, API_ANALYSIS_REVISE_SYSTEM)
        return self._normalize_result(result)

    @staticmethod
    def _normalize_result(result: Any) -> List[Dict[str, Any]]:
        """Normalize LLM JSON response to a list of interface summary dicts."""
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            if "summaries" in result and isinstance(result["summaries"], list):
                return result["summaries"]
            for v in result.values():
                if isinstance(v, list):
                    return v
            return [result]
        logger.warning("API analysis returned unrecognized type: %s", type(result))
        return []
