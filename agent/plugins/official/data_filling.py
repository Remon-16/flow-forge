"""数据填充官方插件 — 为测试用例骨架填充请求数据。

Official data filling plugin: fills request data into test case skeletons.
"""

import logging
import os
from typing import Any, Dict, List, Optional

from plugins.official.agents.data_filler import BizDataFiller, SingleDataFiller
from config.settings import Settings
from knowledge.search import KnowledgeSearch
from plugins.base import CaseAttributeGenerator, PluginDeclaration
from plugins.skill_loader import load_skill_extensions

logger = logging.getLogger(__name__)


class DataFillingPlugin(CaseAttributeGenerator):
    """为用例骨架填充 request_body、request_head、status_code、tag。

    Fills request data into single/biz test case skeletons.
    包装 SingleDataFiller 和 BizDataFiller。
    """

    def __init__(self, settings: Settings, knowledge: Optional[KnowledgeSearch] = None):
        _skills_dir = os.path.join(os.path.dirname(__file__), 'skills')
        _exts = load_skill_extensions('data_filler', settings, _skills_dir)

        self._single_filler = SingleDataFiller(
            settings, knowledge, skill_extensions=_exts,
            case_gen_rules=settings.case_gen_rules,
        )
        self._biz_filler = BizDataFiller(
            settings, knowledge, skill_extensions=_exts,
            case_gen_rules=settings.case_gen_rules,
        )
        self._user_guidance = ""

    @property
    def declaration(self) -> PluginDeclaration:
        return PluginDeclaration(
            plugin_name="data_filling",
            attributes=["request_head", "request_body", "status_code", "tag"],
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
        """填充本批用例的请求数据。Fill request data for a batch of cases."""
        if not cases:
            return cases
        if "sheet_name" in cases[0]:
            return self._biz_filler.fill_batch(
                cases, interfaces, api_summary, api_doc_text, self._user_guidance
            )
        return self._single_filler.fill_batch(
            cases, interfaces, api_summary, api_doc_text, self._user_guidance
        )
