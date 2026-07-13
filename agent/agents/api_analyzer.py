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
    RAW_API_ANALYSIS_SYSTEM,
    RAW_API_ANALYSIS_USER,
    RAW_API_CHUNK_NOTICE,
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

    def analyze_raw_text(
        self, raw_text: str, file_name: str = ""
    ) -> List[Dict[str, Any]]:
        """Analyze raw API document text — identify interfaces first, then summarize.

        Uses token-aware chunking for long documents.  If the text fits within
        the context window, a single call is made.  Otherwise the text is
        split into chunks and results are merged.

        Returns same format as :meth:`analyze`.
        """
        file_label = file_name or "unknown"
        test_prompt = render_prompt(
            RAW_API_ANALYSIS_USER,
            file_name=file_label, raw_text=raw_text,
        )
        input_tokens = self._estimate_input_tokens(RAW_API_ANALYSIS_SYSTEM, test_prompt)

        if input_tokens < self._context_window * self._compression_threshold:
            # Single round — fits comfortably
            logger.info("Analyzing raw API doc text (%d chars)...", len(raw_text))
            result = self.call_llm_json(test_prompt, RAW_API_ANALYSIS_SYSTEM)
            return self._normalize_result(result)

        logger.info(
            "API doc text (%d chars, ~%d tokens) exceeds threshold, "
            "using multi-round chunking",
            len(raw_text), input_tokens,
        )
        return self._process_long_text(
            text=raw_text,
            system_msg=RAW_API_ANALYSIS_SYSTEM,
            chunk_processor=lambda chunk, _: self._analyze_raw_chunk(chunk, file_label),
            result_merger=self._merge_raw_results,
            chunk_notice=RAW_API_CHUNK_NOTICE,
        )

    def _analyze_raw_chunk(self, chunk: str, file_name: str) -> List[Dict[str, Any]]:
        """Process a single chunk of the raw API document."""
        prompt = render_prompt(
            RAW_API_ANALYSIS_USER,
            file_name=file_name, raw_text=chunk,
        )
        result = self.call_llm_json(prompt, RAW_API_ANALYSIS_SYSTEM)
        return self._normalize_result(result)

    @staticmethod
    def _merge_raw_results(
        results: list, _system_msg: str
    ) -> List[Dict[str, Any]]:
        """Merge API analysis results from multiple chunks, deduplicating by api_path+method."""
        seen = set()
        merged = []
        for r in results:
            if isinstance(r, list):
                for item in r:
                    if isinstance(item, dict):
                        key = (item.get("api_path", ""), item.get("method", ""))
                        if key not in seen:
                            seen.add(key)
                            merged.append(item)
            elif isinstance(r, dict):
                key = (r.get("api_path", ""), r.get("method", ""))
                if key not in seen:
                    seen.add(key)
                    merged.append(r)
        logger.info("Merged raw API analysis: %d unique interfaces", len(merged))
        return merged

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
