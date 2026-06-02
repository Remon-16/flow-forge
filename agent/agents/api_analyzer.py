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
- 返回一个 JSON 数组，每个元素是一个接口的摘要对象"""

API_ANALYSIS_USER = """请分析以下接口定义，生成接口摘要：

```json
{{interfaces}}
```

{{extra_context}}"""


class ApiAnalyzer(BaseAgent):
    """Analyze API documentation and produce structured summaries.

    Identifies: description, auth requirements, parameter patterns, uncertainties.
    Supports revision based on user feedback.
    """

    def __init__(self, settings: Settings):
        super().__init__(
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            temperature=0.3,
            max_tokens=settings.llm_max_tokens,
            max_retries=settings.max_retries,
            max_steps=settings.max_steps,
        )

    def analyze(self, interfaces: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Generate API summary for the given interfaces.

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

        if isinstance(result, dict):
            for v in result.values():
                if isinstance(v, list):
                    result = v
                    break
            else:
                result = [result]

        if not isinstance(result, list):
            logger.warning("API analysis returned non-list result, wrapping")
            result = []

        logger.info("API summary generated for %d endpoints", len(result))
        return result

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
            "request_summary, response_summary, notes, uncertainties"
        )

        revise_template = (
            "## 当前接口摘要\n```json\n{{current_summary}}\n```\n\n"
            "## 接口定义\n```json\n{{interfaces}}\n```\n\n"
            "## 用户反馈\n{{feedback}}\n\n"
            "请根据用户反馈修改接口摘要，返回完整的修改后摘要列表。"
        )

        prompt = render_prompt(
            revise_template,
            current_summary=summary_json,
            interfaces=iface_json,
            feedback=feedback,
        )

        logger.info("Revising API summary based on feedback...")
        result = self.call_llm_json(prompt, revise_system)

        if isinstance(result, dict):
            for v in result.values():
                if isinstance(v, list):
                    result = v
                    break
            else:
                result = [result]

        if not isinstance(result, list):
            result = []

        return result
