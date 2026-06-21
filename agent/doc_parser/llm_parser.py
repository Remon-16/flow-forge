"""LLM-based API document parser.

When ``--parse-mode llm`` is selected, this parser sends raw document text
to an LLM and asks it to extract structured ``InterfaceDef`` objects.

Used as an explicit opt-in; not part of the default flow.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from agents.base import BaseAgent
from config.settings import Settings
from models.schema import InterfaceDef
from prompts.doc_parser import DOC_PARSER_SYSTEM, DOC_PARSER_USER

logger = logging.getLogger(__name__)


class DocParserAgent:
    """LLM-based parser that extracts interface definitions from unstructured text.

    Used when ``--parse-mode llm`` is selected. Sends raw document text to the
    configured LLM and asks it to produce a structured ``List[InterfaceDef]``.
    """

    def __init__(self, settings: Settings):
        self._settings = settings
        self._agent = BaseAgent(
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            temperature=0.1,
            max_tokens=settings.llm_max_tokens,
            max_retries=2,
            max_steps=1,
            base_url=settings.llm_base_url,
            context_window=settings.llm_context_window,
            max_output_tokens=settings.llm_max_output_tokens,
            compression_threshold=settings.llm_context_compression_threshold,
            rate_limit_delay=settings.llm_rate_limit_delay,
            retry_base_delay=settings.llm_retry_base_delay,
            max_concurrency=settings.llm_max_concurrency,
        )

    def parse(
        self,
        raw_text: str,
        file_name: str = "",
        file_type_hint: str = "",
    ) -> List[InterfaceDef]:
        """Extract interface definitions from raw document text via LLM.

        Args:
            raw_text: The raw document text.
            file_name: Original file name for context.
            file_type_hint: Format hint (e.g. "PDF", "DOCX", "Markdown").

        Returns:
            List of InterfaceDef objects. Empty list if nothing found.
        """
        if not raw_text or not raw_text.strip():
            logger.warning("DocParserAgent received empty text, returning []")
            return []

        test_prompt = DOC_PARSER_USER.format(
            file_name=file_name or "unknown",
            raw_text=raw_text,
            file_type_hint=file_type_hint or "未知格式",
        )
        input_tokens = self._agent._estimate_input_tokens(DOC_PARSER_SYSTEM, test_prompt)

        if input_tokens < self._agent._context_window * self._agent._compression_threshold:
            # Single round
            try:
                result = self._agent.call_llm_json(test_prompt, DOC_PARSER_SYSTEM)
                return self._parse_response(result)
            except Exception as e:
                logger.error("DocParserAgent LLM call failed: %s", e)
                return []

        # Token-aware chunking
        logger.info(
            "Doc text (%d chars, ~%d tokens) exceeds threshold, chunking",
            len(raw_text), input_tokens,
        )
        return self._agent._process_long_text(
            text=raw_text,
            system_msg=DOC_PARSER_SYSTEM,
            chunk_processor=lambda chunk, _: self._parse_chunk(chunk, file_name, file_type_hint),
            result_merger=self._merge_parsed_interfaces,
            chunk_notice="[这是API文档的一块，后面还有内容。请提取本块中的接口定义。]",
        )

    def _parse_chunk(
        self, chunk: str, file_name: str, file_type_hint: str
    ) -> list:
        """Parse a single chunk of the document."""
        prompt = DOC_PARSER_USER.format(
            file_name=file_name or "unknown",
            raw_text=chunk,
            file_type_hint=file_type_hint or "未知格式",
        )
        try:
            result = self._agent.call_llm_json(prompt, DOC_PARSER_SYSTEM)
            return self._parse_response(result)
        except Exception as e:
            logger.warning("DocParserAgent chunk parse failed: %s", e)
            return []

    @staticmethod
    def _merge_parsed_interfaces(results: list, _system_msg: str) -> list:
        """Merge interface lists from multiple chunks, deduplicating by test_id."""
        seen = set()
        merged = []
        for r in results:
            if isinstance(r, list):
                for iface in r:
                    tid = iface.test_id if hasattr(iface, "test_id") else ""
                    if tid not in seen:
                        seen.add(tid)
                        merged.append(iface)
        logger.info("Merged %d unique interfaces from %d chunks", len(merged), len(results))
        return merged

    def _parse_response(self, raw: Any) -> List[InterfaceDef]:
        """Normalize LLM JSON response into InterfaceDef objects.

        Handles: direct array, {"interfaces": [...]}, {"api_definitions": [...]},
        or a single interface object.
        """
        items: List[Dict] = []

        if isinstance(raw, list):
            items = raw
        elif isinstance(raw, dict):
            for key in ("interfaces", "api_definitions", "apis", "endpoints"):
                if key in raw and isinstance(raw[key], list):
                    items = raw[key]
                    break
            if not items and "url" in raw:
                items = [raw]

        if not items:
            logger.warning("DocParserAgent returned no recognizable interface list")
            return []

        interfaces: List[InterfaceDef] = []
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            try:
                method = str(item.get("method", "GET")).upper()
                url = str(item.get("url", ""))
                test_id = str(item.get("test_id", ""))

                if not test_id:
                    clean = (
                        url.strip("/")
                        .replace("/", "_")
                        .replace("-", "_")
                        .replace("{", "")
                        .replace("}", "")
                        .lower()
                    )
                    test_id = (
                        f"api_{clean}_{method.lower()}"
                        if clean
                        else f"api_extracted_{idx}_{method.lower()}"
                    )

                if not url and not test_id:
                    continue

                interfaces.append(InterfaceDef(
                    test_id=test_id,
                    api_name=str(item.get("api_name", item.get("name", ""))),
                    app_name=str(item.get("app_name", item.get("app", "default"))),
                    method=method,
                    url=url,
                    request_head=dict(item.get("request_head", item.get("headers", {})) or {}),
                    request_body=dict(item.get("request_body", item.get("body", item.get("params", {}))) or {}),
                    status_code=int(item.get("status_code", 200)),
                    assert_dict=dict(item.get("assert_dict", item.get("assertion", {})) or {}),
                    remark=str(item.get("remark", item.get("note", item.get("description", "")))),
                ))
            except Exception as e:
                logger.warning("Failed to parse interface item %d: %s", idx, e)
                continue

        logger.info("DocParserAgent extracted %d interfaces", len(interfaces))
        return interfaces
