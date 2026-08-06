"""需求分析节点 — 从需求文档中提取结构化信息。

analyze_requirement node: extracts structured info from requirement documents.
"""

import logging
import os

from agents.requirement_analyzer import RequirementAnalyzer
from graph.state import GraphState
from plugins.skill_loader import load_skill_extensions

from . import helpers as _h
from .helpers import _, _step, _sl, save_pipeline_artifact, save_pipeline_state, save_snapshot

logger = logging.getLogger(__name__)


def analyze_requirement_node(state: GraphState) -> GraphState:
    """运行需求分析器，支持多文档独立分析后合并。

    Run the requirement analyzer, with per-document independent analysis and merge.
    """
    state.setdefault("errors", [])

    texts = state.get("requirement_texts", [])
    if not texts:
        state["requirement_analysis"] = {
            "business_flows": [], "roles": [], "constraints": [], "exceptions": [],
        }
        return state

    logger.info(_step("analyze_requirement", "pipeline.analyze_req"))
    logger.info(_("req.analyzing", model=_h._settings.llm_model))
    if _sl():
        _sl().log_node_start("analyze_requirement", "3/9")

    _skills_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'skills', 'builtin')
    _exts = load_skill_extensions('requirement_analyzer', _h._settings, _skills_dir)
    agent = RequirementAnalyzer(_h._settings, _h._knowledge, skill_extensions=_exts)

    if len(texts) == 1:
        # 单文档：直接分析 / Single doc: direct analysis
        result = agent.analyze(texts[0])
    else:
        # 多文档：逐文件独立分析后合并 / Multi-doc: per-file analysis then merge
        all_results = []
        for i, text in enumerate(texts):
            if not text.strip():
                continue
            logger.info(f"Analyzing requirement doc {i+1}/{len(texts)} ({len(text)} chars)")
            result = agent.analyze(text)
            all_results.append(result)
        result = agent._merge_analyses(all_results, "")

    state["requirement_analysis"] = result

    memory_dir = state.get("memory_dir", "")
    if memory_dir:
        save_snapshot(memory_dir, "requirement_analysis.json", result)
        save_pipeline_artifact(memory_dir, "requirement_analysis.json", result)
        save_pipeline_state(memory_dir, "analyze_requirement")

    flows = len(result.get("business_flows", []))
    roles = len(result.get("roles", []))
    logger.info(_("req.result", flows=flows, roles=roles))
    if _sl():
        _sl().log_node_end("analyze_requirement")

    return state
