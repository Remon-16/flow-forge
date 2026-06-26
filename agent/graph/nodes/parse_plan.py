"""计划解析节点 — 将确认的 plan.md 解析为结构化 TestPlan。

parse_plan node: parses confirmed plan.md into a structured TestPlan.
"""

import logging
import os

from agents.plan_parser import PlanParser
from graph.state import GraphState
from plugins.skill_loader import load_skill_extensions

from .helpers import _settings, _sl, save_pipeline_artifact, save_pipeline_state, save_snapshot

logger = logging.getLogger(__name__)


def parse_plan_node(state: GraphState) -> GraphState:
    """解析确认后的 plan.md 为结构化 TestPlan。

    Parse the confirmed plan.md into a structured TestPlan.
    """
    state.setdefault("errors", [])
    plan_md = state.get("plan_md", "")

    print(_step("parse_plan", "pipeline.parse_plan"))
    print(_("parse_plan.parsing", model=_settings.llm_model))
    if _sl():
        _sl().log_node_start("parse_plan", "6/9")

    _skills_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'skills', 'builtin')
    _exts = load_skill_extensions('plan_parser', _settings, _skills_dir)
    agent = PlanParser(_settings, skill_extensions=_exts)
    plan = agent.parse(plan_md, interfaces=state.get("interfaces", []))

    state["plan_parsed"] = plan

    memory_dir = state.get("memory_dir", "")
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
    print(_("parse_plan.parsed", api_count=api_count, tp_count=tp_count))
    if _sl():
        _sl().log_node_end("parse_plan")

    return state
