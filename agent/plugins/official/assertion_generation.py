"""断言生成官方插件 — 为已填充数据的用例生成断言。

Official assertion generation plugin: generates assert_dict and assert_rules.
"""

import logging
import os
from typing import Any, Dict, List, Optional

from plugins.official.agents.assertion_generator import BizAssertionGenerator, SingleAssertionGenerator
from config.settings import Settings
from knowledge.search import KnowledgeSearch
from plugins.base import CaseAttributeGenerator, PluginDeclaration
from plugins.skill_loader import load_skill_extensions

logger = logging.getLogger(__name__)


class AssertionGenerationPlugin(CaseAttributeGenerator):
    """为用例生成 assert_dict 和 assert_rules。

    Generates assertions for single/biz test cases.
    包装 SingleAssertionGenerator 和 BizAssertionGenerator。
    """

    def __init__(self, settings: Settings, knowledge: Optional[KnowledgeSearch] = None):
        _skills_dir = os.path.join(os.path.dirname(__file__), 'skills')
        _exts = load_skill_extensions('assertion_generator', settings, _skills_dir)

        self._single_gen = SingleAssertionGenerator(
            settings, knowledge, skill_extensions=_exts,
            case_gen_rules=settings.case_gen_rules,
        )
        self._biz_gen = BizAssertionGenerator(
            settings, knowledge, skill_extensions=_exts,
            case_gen_rules=settings.case_gen_rules,
        )
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
