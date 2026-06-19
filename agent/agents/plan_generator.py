"""PlanGenerator: generate Markdown test plan from requirements + API defs."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from .base import BaseAgent
from config.settings import Settings
from knowledge.search import KnowledgeSearch
from models.schema import InterfaceDef
from prompts.plan_generation import PLAN_GENERATION_SYSTEM, PLAN_GENERATION_USER
from prompts.render import render_prompt

logger = logging.getLogger(__name__)


class PlanGenerator(BaseAgent):
    """Generate a test plan in Markdown format combining requirements and API docs."""

    def __init__(self, settings: Settings, knowledge: Optional[KnowledgeSearch] = None):
        super().__init__(
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            max_retries=settings.max_retries,
            max_steps=settings.max_steps,
            base_url=settings.llm_base_url,
            context_window=settings.llm_context_window,
            max_output_tokens=settings.llm_max_output_tokens,
            compression_threshold=settings.llm_context_compression_threshold,
        )
        self._knowledge = knowledge

    def generate(
        self,
        requirement_analysis: Dict[str, Any],
        interfaces: List[InterfaceDef],
        api_summary: List[Dict[str, Any]] | None = None,
        user_guidance: str = "",
        reference_summary: str = "",
    ) -> str:
        """Generate a Markdown test plan.

        Args:
            requirement_analysis: Structured analysis from RequirementAnalyzer.
            interfaces: List of InterfaceDef objects or dicts.
            api_summary: Optional API analysis summary from ApiAnalyzer.
            user_guidance: Optional user guidance from --prompt CLI flag.
            reference_summary: Optional summary of existing coverage from --reference-dir.

        Returns the full plan as a Markdown string.
        """
        # Serialize interfaces
        iface_dicts = []
        for iface in interfaces:
            if isinstance(iface, dict):
                iface_dicts.append(iface)
            else:
                iface_dicts.append({
                    "test_id": iface.test_id,
                    "api_name": iface.api_name,
                    "app_name": iface.app_name,
                    "method": iface.method,
                    "url": iface.url,
                    "request_head": iface.request_head,
                    "request_body": iface.request_body,
                    "status_code": iface.status_code,
                    "assert_dict": iface.assert_dict,
                    "remark": iface.remark,
                })

        requirement_json = json.dumps(requirement_analysis, ensure_ascii=False, indent=2)
        iface_json = json.dumps(iface_dicts, ensure_ascii=False, indent=2)
        api_summary_json = json.dumps(api_summary, ensure_ascii=False, indent=2) if api_summary else "无接口分析摘要"

        prompt = render_prompt(
            PLAN_GENERATION_USER,
            requirement_analysis=requirement_json,
            interface_defs=iface_json,
            api_summary=api_summary_json,
            user_guidance=user_guidance,
            reference_summary=reference_summary or "(无)",
        )

        # Conditionally append knowledge context
        if self._knowledge is not None:
            docs = self._knowledge.search("test plan generation best practices", n_results=3)
            if docs:
                knowledge_context = "\n---\n".join(docs)
                prompt += f"\n\n## 知识库参考\n{knowledge_context}"

        # Token check
        input_tokens = self._estimate_input_tokens(PLAN_GENERATION_SYSTEM, prompt)
        if input_tokens > self._context_window:
            raise ValueError(
                f"Plan generation input exceeds context window: "
                f"{input_tokens} / {self._context_window} tokens. "
                f"Consider reducing the number of interfaces or splitting the task."
            )

        logger.info(
            "Generating test plan for %d interfaces (~%d tokens)...",
            len(interfaces), input_tokens,
        )
        plan_md = self.call_llm(prompt, PLAN_GENERATION_SYSTEM)
        logger.info("Test plan generated (%d chars)", len(plan_md))
        return plan_md
