"""ApiAnalyzer: analyze API docs for completeness and generate structured summaries."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from .base import BaseAgent
from config.settings import Settings

logger = logging.getLogger(__name__)

API_ANALYSIS_SYSTEM = """你是一个专业的接口文档分析专家。分析给定的接口列表，生成接口摘要。

对每个接口识别：
- 接口用途（description）
- 是否需要认证 Token（need_token）
- 认证方式（auth_type：none / Bearer Token / Cookie / Basic Auth / 不确定）
- 请求参数概要（request_summary）
- 响应内容概要（response_summary）
- 注意事项（notes）
- 不确定的地方（uncertainties，向用户确认的问题列表）

注意：
- 如果接口文档中缺少描述，请推断并在 uncertainties 中标注
- 认证方式的推断：如果接口有 Authorization 头参数或 security 定义，标记 need_token=true
- 对不确定的推断，务必在 uncertainties 中列出具体问题
- 返回一个 JSON 对象，包含 "summaries" 字段，其值为接口摘要数组
- 格式示例：{"summaries": [{"api_path": "/api/xxx", "method": "POST", ...}]}
- 如果没有任何接口，返回 {"summaries": []}"""

API_ANALYSIS_USER = """请分析以下接口定义，生成接口摘要：

```json
{{interfaces}}
```

{{extra_context}}"""


# --- Raw text analysis prompt (for --parse-mode raw) ---
RAW_API_ANALYSIS_SYSTEM = """你是一个专业的接口文档分析专家。你会收到一份 API 文档的原文（可能是 OpenAPI 规范、Markdown 表格、手写文档等任意格式），你的任务是：

1. 首先从文档原文中识别所有 API 接口定义（HTTP 方法 + URL 路径 + 参数 + 响应）
2. 然后对每个识别到的接口生成结构化摘要

对每个接口识别：
- api_path: 接口 URL 路径
- method: HTTP 方法 (GET/POST/PUT/DELETE/PATCH)
- description: 接口用途简述
- need_token: 是否需要认证 Token (true/false)
- auth_type: 认证方式（none / Bearer Token / Cookie / Basic Auth / 不确定）
- request_summary: 请求参数概要
- response_summary: 响应内容概要
- notes: 注意事项
- uncertainties: 不确定的地方（向用户确认的问题列表）

注意：
- 如果文档原文中缺少描述，请根据 URL 和方法合理推断，并在 uncertainties 中标注
- 认证方式的推断：如果接口有 Authorization 头参数或 security 定义，标记 need_token=true
- 对不确定的推断，务必在 uncertainties 中列出具体问题
- 返回一个 JSON 对象，包含 "summaries" 字段，其值为接口摘要数组
- 格式示例：{"summaries": [{"api_path": "/api/xxx", "method": "GET", ...}]}
- 如果文档中完全没有 API 接口定义，返回 {"summaries": []}"""

RAW_API_ANALYSIS_USER = """请分析以下 API 文档原文，先识别其中包含的所有接口，再对每个接口生成摘要。

## 文件名
{file_name}

## 文档原文
{raw_text}

请返回 JSON 对象格式的接口摘要列表，格式为 {{"summaries": [...]}}。"""


class ApiAnalyzer(BaseAgent):
    """Analyze API documentation and produce structured summaries.

    Identifies: description, auth requirements, parameter patterns, uncertainties.
    Supports revision based on user feedback.
    Supports both structured interfaces (rule/llm modes) and raw text (raw mode).
    """

    def __init__(self, settings: Settings):
        super().__init__(
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            temperature=0.3,
            max_tokens=settings.llm_max_tokens,
            max_retries=settings.max_retries,
            max_steps=settings.max_steps,
            base_url=settings.llm_base_url,
            context_window=settings.llm_context_window,
            max_output_tokens=settings.llm_max_output_tokens,
            compression_threshold=settings.llm_context_compression_threshold,
        )
        self._settings = settings

    def analyze(self, interfaces: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Generate API summary for the given structured interfaces.

        Returns list of dicts with keys:
            api_path, method, description, need_token, auth_type,
            request_summary, response_summary, notes, uncertainties
        """
        from prompts.render import render_prompt

        iface_json = json.dumps(interfaces, ensure_ascii=False, indent=2)
        prompt = render_prompt(
            API_ANALYSIS_USER,
            interfaces=iface_json,
            extra_context="",
        )

        logger.info("Analyzing %d interfaces...", len(interfaces))
        result = self.call_llm_json(prompt, API_ANALYSIS_SYSTEM)
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
        test_prompt = RAW_API_ANALYSIS_USER.format(
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
            chunk_notice="[这是API文档的一块，后面还有内容。请识别本块中的接口并生成摘要。]",
        )

    def _analyze_raw_chunk(self, chunk: str, file_name: str) -> List[Dict[str, Any]]:
        """Process a single chunk of the raw API document."""
        prompt = RAW_API_ANALYSIS_USER.format(
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
        from prompts.render import render_prompt

        iface_json = json.dumps(interfaces, ensure_ascii=False, indent=2)
        summary_json = json.dumps(current_summary, ensure_ascii=False, indent=2)

        revise_system = (
            "你是一个专业的接口文档分析专家。根据用户的反馈意见修改接口摘要。"
            "确保修改后的摘要仍然包含完整的字段："
            "api_path, method, description, need_token, auth_type, "
            "request_summary, response_summary, notes, uncertainties。"
            "返回一个 JSON 对象，包含 \"summaries\" 字段，其值为修改后的摘要列表。"
        )

        revise_template = (
            "## 当前接口摘要\n```json\n{{current_summary}}\n```\n\n"
            "## 接口定义\n```json\n{{interfaces}}\n```\n\n"
            "## 用户反馈\n{{feedback}}\n\n"
            "请根据用户反馈修改接口摘要，返回 JSON 对象格式：{\"summaries\": [...]}"
        )

        prompt = render_prompt(
            revise_template,
            current_summary=summary_json,
            interfaces=iface_json,
            feedback=feedback,
        )

        logger.info("Revising API summary based on feedback...")
        result = self.call_llm_json(prompt, revise_system)
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
