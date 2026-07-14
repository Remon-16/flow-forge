"""处理器分配官方插件 — 为已填充数据的用例分配 DB 前置/后置处理器。

Official processor assignment plugin: assigns DB pre/post-processors to data-filled cases.

此插件在 DataFillingPlugin 之后、AssertionGenerationPlugin 之前运行。
通过 Skill 告知 LLM 可用的 DB 处理器列表，让 LLM 为每个用例决定
需要哪些 preprocessors / postprocessors。

This plugin runs after DataFillingPlugin and before AssertionGenerationPlugin.
It uses Skills to inform the LLM about available DB processors, and the LLM
decides which preprocessors/postprocessors to assign to each case.
"""

import logging
import os
from typing import Any, Dict, List, Optional

from plugins.official.agents.processor_selector import (
    SingleProcessorSelector,
    BizProcessorSelector,
)
from config.settings import Settings
from knowledge.search import KnowledgeSearch
from plugins.base import CaseAttributeGenerator, PluginDeclaration
from plugins.skill_loader import load_skill_extensions

logger = logging.getLogger(__name__)


class ProcessorPlugin(CaseAttributeGenerator):
    """为用例分配 preprocessors 和 postprocessors。

    Assigns preprocessors and postprocessors to test cases.
    包装 SingleProcessorSelector 和 BizProcessorSelector。
    """

    def __init__(self, settings: Settings, knowledge: Optional[KnowledgeSearch] = None):
        _skills_dir = os.path.join(os.path.dirname(__file__), 'skills')
        _exts = load_skill_extensions('processor_selector', settings, _skills_dir)

        self._single_selector = SingleProcessorSelector(
            settings, knowledge, skill_extensions=_exts,
            case_gen_validation=settings.case_gen_validation,
        )
        self._biz_selector = BizProcessorSelector(
            settings, knowledge, skill_extensions=_exts,
            case_gen_validation=settings.case_gen_validation,
        )
        self._user_guidance = ""

    @property
    def declaration(self) -> PluginDeclaration:
        return PluginDeclaration(
            plugin_name="processor_selection",
            attributes=["preprocessors", "postprocessors"],
            applies_to_single=True,
            applies_to_biz=True,
            max_retries=3,
            error_strategy="warn",  # 处理器分配失败应警告而非终止 / warn rather than abort
        )

    def set_user_guidance(self, guidance: str) -> None:
        """设置用户指导文本。Set user guidance for generation."""
        self._user_guidance = guidance

    def generate(
        self,
        cases: List[Dict[str, Any]],
        interfaces: List[Dict[str, Any]],
        api_summary: List[Dict[str, Any]],
        api_doc_text: str,
    ) -> List[Dict[str, Any]]:
        """为本批用例分配处理器。Assign processors for a batch of cases."""
        if not cases:
            return cases
        # 业务流用例：第一个元素有 sheet_name / Biz flow: first element has sheet_name
        if "sheet_name" in cases[0]:
            return self._biz_selector.fill_batch(
                cases, interfaces, api_summary, self._user_guidance
            )
        return self._single_selector.fill_batch(
            cases, interfaces, api_summary, self._user_guidance
        )
