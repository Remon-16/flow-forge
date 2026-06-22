"""断言生成官方插件 — 为已填充数据的用例生成断言。

Official assertion generation plugin: generates assert_dict and assert_rules.
"""

import logging
from typing import Any, Dict, List, Optional

from agents.assertion_generator import BizAssertionGenerator, SingleAssertionGenerator
from config.settings import Settings
from knowledge.search import KnowledgeSearch
from plugins.base import CaseAttributeGenerator, PluginDeclaration

logger = logging.getLogger(__name__)


class AssertionGenerationPlugin(CaseAttributeGenerator):
    """为用例生成 assert_dict 和 assert_rules。

    Generates assertions for single/biz test cases.
    包装 SingleAssertionGenerator 和 BizAssertionGenerator。
    """

    def __init__(self, settings: Settings, knowledge: Optional[KnowledgeSearch] = None):
        self._single_gen = SingleAssertionGenerator(settings, knowledge)
        self._biz_gen = BizAssertionGenerator(settings, knowledge)
        self._user_guidance = ""

    @property
    def declaration(self) -> PluginDeclaration:
        return PluginDeclaration(
            plugin_name="assertion_generation",
            attributes=["assert_dict", "assert_rules"],
            applies_to_single=True,
            applies_to_biz=True,
            max_retries=3,
            error_strategy="fail",
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
        """为本批用例生成断言。Generate assertions for a batch of cases."""
        if not cases:
            return cases
        if "sheet_name" in cases[0]:
            return self._biz_gen.fill_batch(
                cases, interfaces, api_summary, self._user_guidance
            )
        return self._single_gen.fill_batch(
            cases, interfaces, api_summary, self._user_guidance
        )
