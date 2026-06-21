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

logger = logging.getLogger(__name__)


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

    print("\n[开始] Flow Forge 智能体流水线启动...")
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
            choice = input(
                "\n是否需要澄清以上问题？(输入修改意见 / skip 跳过): "
            ).strip()
            if choice.lower() == "skip":
                result = _resume("skip")
            elif choice:
                result = _resume(choice)
            else:
                result = _resume("skip")

        elif pending == "human_confirm":
            choice = input(
                "\n是否批准此测试计划？\n"
                "  y = 批准，继续执行用例生成\n"
                "  n = 提出文字修改意见\n"
                "  r = 按批注文件修改（需先在 Studio 中对 plan.md 添加批注）\n"
                "请输入 (y/n/r): "
            ).strip().lower()
            if choice == "y":
                print("\n计划已批准，继续执行用例生成...")
                result = _resume("approved")
            elif choice == "n":
                feedback = input("请描述需要修改的内容: ").strip()
                if not feedback:
                    print("修改意见不能为空，请重新输入。")
                    continue
                print("\n正在根据反馈修改计划...\n")

                snapshot = graph.get_state(config)
                state = dict(snapshot.values)
                state["plan_feedback"] = feedback
                state["plan_feedback_type"] = "text"
                state["plan_confirmed"] = False
                revised_state = revise_plan_node(state)
                graph.update_state(config, revised_state, as_node="revise_plan")
                print("\n[审核] 计划已修改，请再次审核...")
            elif choice == "r":
                snapshot = graph.get_state(config)
                state = dict(snapshot.values)
                memory_dir = state.get("memory_dir", "./output/memory")
                comments_path = Path(memory_dir) / "plan_comments.json"

                if not comments_path.exists():
                    print(f"\n错误: 未找到批注文件: {comments_path.resolve()}")
                    print("请先在 Studio 中对测试计划添加批注。")
                    continue

                try:
                    annotations = _json.loads(comments_path.read_text("utf-8"))
                except Exception as e:
                    print(f"\n错误: 批注文件解析失败: {e}")
                    continue

                if not annotations:
                    print("\n错误: 批注文件为空，请添加批注后重试。")
                    continue

                print(f"\n已读取 {len(annotations)} 条批注:")
                for i, ann in enumerate(annotations[:5], 1):
                    print(f"  {i}. [行{ann.get('line_number', '?')}] {ann.get('review_comment', '')[:60]}")
                if len(annotations) > 5:
                    print(f"  ... 共 {len(annotations)} 条")

                print("\n正在根据批注修改计划...\n")

                state["plan_feedback_type"] = "annotations"
                state["plan_annotations"] = annotations
                state["plan_confirmed"] = False
                revised_state = revise_plan_node(state)
                graph.update_state(config, revised_state, as_node="revise_plan")

                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                history_dir = Path(memory_dir) / "history-comments"
                history_dir.mkdir(parents=True, exist_ok=True)
                archive_name = f"plan_comments_{ts}.json"
                comments_path.rename(history_dir / archive_name)
                print(f"批注文件已归档: history-comments/{archive_name}")
                print("\n[审核] 计划已修改，请再次审核...")
            else:
                print("无效输入，请输入 y、n 或 r。")
        else:
            break

    return result or {}
