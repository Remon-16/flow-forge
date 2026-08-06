"""CLI 交互 — 人工审核和中断处理循环。

CLI interactive: human review loop and interrupt handling.
"""

import json as _json
import logging
from datetime import datetime
from pathlib import Path

from langgraph.errors import GraphInterrupt
from langgraph.types import Command

from graph.nodes.review import revise_plan_node
from graph.state import GraphState
from i18n import _

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# 中断处理辅助函数 / Interrupt handler helpers
# ------------------------------------------------------------------

def _handle_api_clarification(graph, config, _resume):
    """处理 API 分析确认询问。Handle API analysis clarification prompt."""
    choice = input(_("review.prompt_clarify")).strip()
    if choice.lower() == "skip":
        return _resume("skip")
    elif choice:
        return _resume(choice)
    else:
        return _resume("skip")


def _handle_text_revision(graph, config, feedback: str) -> None:
    """处理用户文字反馈，调用 revise_plan_node 修订计划。

    Handle text feedback: set plan_feedback state, call revise_plan_node,
    and update graph checkpoint.
    """
    logger.info(_("review.revising"))

    snapshot = graph.get_state(config)
    state = dict(snapshot.values)
    state["plan_feedback"] = feedback
    state["plan_feedback_type"] = "text"
    state["plan_confirmed"] = False
    revised_state = revise_plan_node(state)
    graph.update_state(config, revised_state, as_node="revise_plan")
    logger.info(_("review.revised"))


def _handle_annotation_revision(graph, config) -> bool:
    """处理批注文件修订，返回 True 表示修订成功。

    Handle annotation file revision: read plan_comments.json,
    validate, revise, and archive. Returns True on success.
    """
    snapshot = graph.get_state(config)
    state = dict(snapshot.values)
    memory_dir = state.get("memory_dir", "./output/memory")
    comments_path = Path(memory_dir) / "plan_comments.json"

    if not comments_path.exists():
        logger.info(_("review.annotations_not_found", path=comments_path.resolve()))
        return False

    try:
        annotations = _json.loads(comments_path.read_text("utf-8"))
    except Exception as e:
        logger.info(_("review.annotations_parse_error", error=e))
        return False

    if not annotations:
        logger.info(_("review.annotations_empty"))
        return False

    logger.info(_("review.annotations_read", count=len(annotations)))
    for i, ann in enumerate(annotations[:5], 1):
        logger.info(_("review.annotations_read_item", i=i,
                 line=ann.get("line_number", "?"),
                 comment=ann.get("review_comment", "")[:60]))
    if len(annotations) > 5:
        logger.info(_("review.annotations_read_more", count=len(annotations)))

    logger.info(_("review.revising_annotations"))

    state["plan_feedback_type"] = "annotations"
    state["plan_annotations"] = annotations
    state["plan_confirmed"] = False
    revised_state = revise_plan_node(state)
    graph.update_state(config, revised_state, as_node="revise_plan")

    # Archive the consumed annotations file
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    history_dir = Path(memory_dir) / "history-comments"
    history_dir.mkdir(parents=True, exist_ok=True)
    archive_name = f"plan_comments_{ts}.json"
    comments_path.rename(history_dir / archive_name)
    logger.info(_("review.annotations_archived", path=f"history-comments/{archive_name}"))
    logger.info(_("review.revised"))
    return True


# ------------------------------------------------------------------
# 主交互循环 / Main interactive loop
# ------------------------------------------------------------------

def run_interactive(
    graph,
    initial: GraphState,
    config: dict,
    session_logger=None,
) -> GraphState:
    """处理所有中断点的交互循环。

    Run the graph handling all interrupt points:
    - analyze_api: optional — user may clarify or skip
    - human_confirm: mandatory — approve (y) or reject with feedback (n) or annotations (r)
    """

    def _resume(value):
        try:
            return graph.invoke(Command(resume=value), config)
        except GraphInterrupt:
            return None

    logger.info(_("pipeline.start"))
    if session_logger:
        session_logger.log_event("pipeline_start", stage="interactive")

    try:
        result = graph.invoke(initial, config)
    except GraphInterrupt:
        result = None

    while True:
        snapshot = graph.get_state(config)
        if snapshot is None or not snapshot.next:
            break

        pending = snapshot.next[0] if snapshot.next else ""

        if pending == "analyze_api":
            result = _handle_api_clarification(graph, config, _resume)

        elif pending == "human_confirm":
            # 提示 plan.md 路径, 用户可手动编辑 / Show plan.md path for manual editing
            memory_dir = snapshot.values.get("memory_dir", "")
            if memory_dir:
                plan_path = Path(memory_dir) / "plan.md"
                if plan_path.exists():
                    logger.info(_("review.manual_edit_hint", path=str(plan_path.resolve())))
            choice = input(_("review.prompt_approve")).strip().lower()
            if choice == "y":
                logger.info(_("review.approved"))
                result = _resume("approved")
            elif choice == "n":
                feedback = input(_("review.describe_changes")).strip()
                if not feedback:
                    logger.info(_("review.feedback_empty"))
                    continue
                _handle_text_revision(graph, config, feedback)
            elif choice == "r":
                if not _handle_annotation_revision(graph, config):
                    continue
            else:
                logger.info(_("review.invalid_input"))
        else:
            break

    return result or {}
