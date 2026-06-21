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

logger = logging.getLogger(__name__)

DOC_PARSER_SYSTEM = """你是一个 API 文档解析专家。你的任务是从非结构化的文档文本中提取 API 接口定义。

提取规则：
1. 识别所有 API 端点（HTTP 方法 + URL 路径）
2. 对每个端点，提取以下信息：
   - test_id: 自动生成，格式为 api_{path}_{method}，例如 api_user_login_post
   - api_name: 接口名称/描述
   - app_name: 所属应用/模块名，若无法判断填 "default"
   - method: HTTP 方法 (GET/POST/PUT/DELETE/PATCH)
   - url: URL 路径
   - request_head: 请求头，JSON 对象，如 {"Content-Type": "application/json"}
   - request_body: 请求体参数，JSON 对象，列出字段名和示例值
   - status_code: 预期成功状态码，默认 200
   - assert_dict: 断言检查项，JSON 对象，如 {"status_code": 200}
   - remark: 备注/补充说明

3. 对于无法确定的字段，使用合理的默认值
4. 如果文档中描述了请求参数，用 "字段名": "示例值" 的格式填入 request_body
5. 如果文档中描述了响应字段，将其加入 assert_dict 作为检查项

请以严格的 JSON 对象格式返回，对象中包含 "interfaces" 字段，其值为接口定义数组：
```json
{
  "interfaces": [
    {
      "test_id": "api_user_login_post",
      "api_name": "用户登录",
      "app_name": "user_management",
      "method": "POST",
      "url": "/api/user/login",
      "request_head": {"Content-Type": "application/json"},
      "request_body": {"username": "string", "password": "string"},
      "status_code": 200,
      "assert_dict": {"status_code": 200, "data.token": "not_empty"},
      "remark": "用户登录接口"
    }
  ]
}
```

只返回 JSON 对象，不要包含其他文字说明。"""

DOC_PARSER_USER = """请从以下 API 文档内容中提取所有接口定义。

## 文件名
{file_name}

## 文档内容
{raw_text}

## 提示
- 文件类型提示: {file_type_hint}
- 请仔细阅读全文，不要遗漏任何接口
- 如果文档内容看起来不包含 API 定义，请返回空对象 {"interfaces": []}

请返回 JSON 对象，其中 "interfaces" 字段包含接口定义列表。"""


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
