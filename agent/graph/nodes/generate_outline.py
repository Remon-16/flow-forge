"""轮廓生成节点 — 基于需求分析和接口列表生成轻量级 JSON 轮廓。

generate_outline node: generates a lightweight JSON outline from requirement analysis + interface list.
"""

import logging
import os

from agents.plan_generator import PlanGenerator
from graph.state import GraphState
from plugins.skill_loader import load_skill_extensions

from . import helpers as _h
from .helpers import _, _step, _sl, save_pipeline_artifact, save_pipeline_state

logger = logging.getLogger(__name__)


def generate_outline_node(state: GraphState) -> GraphState:
    """生成测试计划轮廓 JSON，用于指导后续分块计划生成。

    Generate a lightweight test plan outline (JSON) to guide chunked plan generation.
    The outline groups interfaces by business domain and lists business flows.
    """
    state.setdefault("errors", [])

    analysis = state.get("requirement_analysis", {})
    interfaces = state.get("interfaces", [])
    api_summary = state.get("api_summary", [])
    user_guidance = state.get("user_guidance", "")

    # 构造轻量接口列表（仅名称/URL，不含完整 body）/ Build lightweight interface list
    interface_names = []
    for iface in interfaces:
        if isinstance(iface, dict):
            interface_names.append({
                "test_id": iface.get("test_id", ""),
                "api_name": iface.get("api_name", ""),
                "method": iface.get("method", "GET"),
                "url": iface.get("url", ""),
            })
        else:
            interface_names.append({
                "test_id": getattr(iface, "test_id", ""),
                "api_name": getattr(iface, "api_name", ""),
                "method": getattr(iface, "method", "GET"),
                "url": getattr(iface, "url", ""),
            })

    # 加载 skill 扩展 / Load skill extensions
    _skills_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        'skills', 'builtin',
    )
    _exts = load_skill_extensions('plan_generator', _h._settings, _skills_dir)

    logger.info(_step("generate_outline", "pipeline.generate_outline"))
    logger.info(_("plan.generating_outline"))

    if _sl():
        _sl().log_node_start("generate_outline", "5/10")

    agent = PlanGenerator(_h._settings, _h._knowledge, skill_extensions=_exts)
    outline = agent.generate_outline(
        requirement_analysis=analysis,
        interface_names=interface_names,
        api_summary=api_summary,
        user_guidance=user_guidance,
    )

    state["plan_outline"] = outline

    # 保存轮廓到 memory_dir / Save outline for resume
    memory_dir = state.get("memory_dir", "")
    if memory_dir:
        save_pipeline_artifact(memory_dir, "plan_outline.json", outline)
        save_pipeline_state(memory_dir, "generate_outline")

    groups = len(outline.get("api_groups", []))
    flows = len(outline.get("biz_flows", []))
    logger.info(_("plan.outline_generated", groups=groups, flows=flows))

    if _sl():
        _sl().log_node_end("generate_outline")

    return state
