"""需求分析节点 — 从需求文档中提取结构化信息。

analyze_requirement node: extracts structured info from requirement documents.
"""

import logging
import os

from agents.requirement_analyzer import RequirementAnalyzer
from graph.state import GraphState
from plugins.skill_loader import load_skill_extensions

from .helpers import _settings, _knowledge, _sl, save_pipeline_artifact, save_pipeline_state, save_snapshot

logger = logging.getLogger(__name__)


def analyze_requirement_node(state: GraphState) -> GraphState:
    """运行需求分析器（单次 LLM 调用）。

    Run the requirement analyzer (single-shot LLM call).
    """
    state.setdefault("errors", [])

    text = state.get("requirement_text", "")
    if not text.strip():
        state["requirement_analysis"] = {
            "business_flows": [], "roles": [], "constraints": [], "exceptions": [],
        }
        return state

    print(_step("analyze_requirement", "pipeline.analyze_req"))
    print(_("req.analyzing", model=_settings.llm_model))
    if _sl():
        _sl().log_node_start("analyze_requirement", "3/9")

    _skills_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'skills', 'builtin')
    _exts = load_skill_extensions('requirement_analyzer', _settings, _skills_dir)
    agent = RequirementAnalyzer(_settings, _knowledge, skill_extensions=_exts)
    result = agent.analyze(text)
    state["requirement_analysis"] = result

    memory_dir = state.get("memory_dir", "")
    if memory_dir:
        save_snapshot(memory_dir, "requirement_analysis.json", result)
        save_pipeline_artifact(memory_dir, "requirement_analysis.json", result)
        save_pipeline_state(memory_dir, "analyze_requirement")

    flows = len(result.get("business_flows", []))
    roles = len(result.get("roles", []))
    print(_("req.result", flows=flows, roles=roles))
    if _sl():
        _sl().log_node_end("analyze_requirement")

    return state
