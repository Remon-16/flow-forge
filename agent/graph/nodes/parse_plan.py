"""计划解析节点 — 从 plan_sections.json 解析为结构化 TestPlan。

parse_plan node: parses plan_sections.json into a structured TestPlan.
"""

import json
import logging
import os
from pathlib import Path

from agents.plan_parser import PlanParser
from graph.state import GraphState
from plugins.skill_loader import load_skill_extensions

from . import helpers as _h
from .helpers import _, _step, _sl, save_pipeline_artifact, save_pipeline_state, save_snapshot

logger = logging.getLogger(__name__)


def parse_plan_node(state: GraphState) -> GraphState:
    """从 plan_sections.json 解析为结构化 TestPlan。

    Parse plan_sections.json into a structured TestPlan.
    plan.md 不再被读取 — plan_sections.json 是唯一数据源。
    plan.md is no longer read — plan_sections.json is the only data source.
    """
    state.setdefault("errors", [])
    memory_dir = state.get("memory_dir", "")

    logger.info(_step("parse_plan", "pipeline.parse_plan"))
    logger.info(_("parse_plan.parsing", model=_h._settings.llm_model))
    if _sl():
        _sl().log_node_start("parse_plan", "6/9")

    # 从 plan_sections.json 加载 sections / Load sections from plan_sections.json
    sections = {}
    if memory_dir:
        sections_path = Path(memory_dir) / "plan_sections.json"
        if sections_path.exists():
            sections = json.loads(sections_path.read_text(encoding="utf-8"))
        else:
            logger.warning("plan_sections.json not found at %s", sections_path)

    _skills_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'skills', 'builtin')
    _exts = load_skill_extensions('plan_parser', _h._settings, _skills_dir)
    agent = PlanParser(_h._settings, skill_extensions=_exts)
    plan = agent.parse_from_sections(sections, interfaces=state.get("interfaces", []),
                                      case_type=state.get("case_type", "both"))

    state["plan_parsed"] = plan

    if memory_dir:
        from dataclasses import asdict as dataclass_asdict
        try:
            plan_dict = dataclass_asdict(plan)
        except Exception:
            plan_dict = {"business_summary": plan.business_summary}
        save_snapshot(memory_dir, "plan_parsed.json", plan_dict)
        save_pipeline_artifact(memory_dir, "plan_parsed.json", plan_dict)
        save_pipeline_state(memory_dir, "parse_plan")

    api_count = len(plan.api_definitions)
    tp_count = sum(len(v) for v in plan.single_test_points.values())
    logger.info(_("parse_plan.parsed", api_count=api_count, tp_count=tp_count))
    if _sl():
        _sl().log_node_end("parse_plan")

    return state
