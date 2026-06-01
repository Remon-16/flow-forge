"""PlanGenerator: generate Markdown test plan from requirements + API defs."""

import json
import logging
from typing import Any, Dict, List

from .base import BaseAgent
from config.settings import Settings
from knowledge.rag import RAGKnowledgeBase
from models.schema import InterfaceDef
from prompts.plan_generation import PLAN_GENERATION_SYSTEM, PLAN_GENERATION_USER
from prompts.render import render_prompt

logger = logging.getLogger(__name__)


class PlanGenerator(BaseAgent):
    """Generate a test plan in Markdown format combining requirements and API docs."""

    def __init__(self, settings: Settings, rag: RAGKnowledgeBase):
        super().__init__(
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            max_retries=settings.max_retries,
            max_steps=settings.max_steps,
        )
        self._rag = rag

    def generate(
        self,
        requirement_analysis: Dict[str, Any],
        interfaces: List[InterfaceDef],
    ) -> str:
        """Generate a Markdown test plan.

        Returns the full plan as a Markdown string.
        """
        # Serialize interfaces
        iface_dicts = []
        for iface in interfaces:
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

        rag_docs = self._rag.query(
            "test plan generation best practices", n_results=3
        )
        rag_context = "\n---\n".join(rag_docs) if rag_docs else "无相关知识库参考"

        prompt = render_prompt(
            PLAN_GENERATION_USER,
            requirement_analysis=requirement_json,
            interface_defs=iface_json,
            rag_context=rag_context,
        )

        logger.info(
            "Generating test plan for %d interfaces...", len(interfaces)
        )
        plan_md = self.call_llm(prompt, PLAN_GENERATION_SYSTEM)
        logger.info("Test plan generated (%d chars)", len(plan_md))
        return plan_md
