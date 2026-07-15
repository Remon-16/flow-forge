"""Studio 子进程桥接 — JSON 协议通信。

Studio subprocess bridge: JSON protocol communication over stdout/stdin.

协议规范 / Protocol specification:
  stdout: 每行一个完整 JSON 事件（用 \\n 分隔）
          One complete JSON event per line (delimited by \\n)
  stdin:  每行一个完整 JSON 命令（用 \\n 分隔）
          One complete JSON command per line (delimited by \\n)

事件类型 / Event types (agent → studio):
  {"type":"log","level":"info","message":"..."}
  {"type":"progress","stage":"...","step":"...","detail":"..."}
  {"type":"prompt","id":"p1","kind":"...","message":"...","data":{...}}
  {"type":"complete","data":{"single_cases":N,"biz_flows":N,...}}
  {"type":"error","message":"..."}

命令类型 / Command types (studio → agent):
  {"command":"skip","prompt_id":"..."}
  {"command":"respond","prompt_id":"...","text":"..."}
  {"command":"approve","prompt_id":"..."}
  {"command":"revise_annotations","prompt_id":"..."}
  {"command":"revise_text","prompt_id":"...","text":"..."}
  {"command":"terminate"}
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, Optional

from langgraph.errors import GraphInterrupt
from langgraph.types import Command

from graph.state import GraphState
from i18n import _

logger = logging.getLogger(__name__)


# ============================================================================
# StudioBridge — JSON 协议通信 / JSON protocol communication
# ============================================================================


class StudioBridge:
    """Studio 子进程桥接。

    封装 stdout JSON 事件发送和 stdin JSON 命令接收。
    Encapsulates stdout JSON event emission and stdin JSON command reception.

    使用示例 / Usage:
        bridge = StudioBridge()
        bridge.emit("log", level="info", message="Starting...")
        cmd = bridge.wait_for_command()
        if cmd["command"] == "skip":
            ...
    """

    def __init__(self):
        self._prompt_counter: int = 0

    # ------------------------------------------------------------------
    # 内部方法 / Internal methods
    # ------------------------------------------------------------------

    def _next_prompt_id(self) -> str:
        """生成自增 prompt ID / Generate auto-increment prompt ID."""
        self._prompt_counter += 1
        return f"p{self._prompt_counter}"

    def _now_ts(self) -> str:
        """当前时间戳字符串 / Current timestamp string."""
        return datetime.now().strftime("%H:%M:%S")

    # ------------------------------------------------------------------
    # 公开方法 / Public methods
    # ------------------------------------------------------------------

    def emit(self, event_type: str, **kwargs: Any) -> None:
        """发送 JSON 事件到 stdout。

        Send a JSON event to stdout. Each event is written as one complete
        JSON line followed by a newline, then flushed immediately.

        Args:
            event_type: 事件类型 / Event type (log, progress, prompt, complete, error).
            **kwargs:  附加字段，合并到 JSON 对象中 / Additional fields merged into the JSON object.
        """
        event: Dict[str, Any] = {"type": event_type, "ts": self._now_ts()}
        event.update(kwargs)
        line = json.dumps(event, ensure_ascii=False)
        sys.stdout.write(line + "\n")
        sys.stdout.flush()

    def wait_for_command(self) -> dict:
        """从 stdin 读取一条 JSON 命令（阻塞）。

        Read one JSON command from stdin (blocking).
        如果 stdin 关闭（EOF），返回 terminate 命令。
        If stdin is closed (EOF), returns a terminate command.

        Returns:
            dict: 命令对象 / Command object, e.g. {"command": "skip", "prompt_id": "p1"}.
        """
        line = sys.stdin.readline()
        if not line:
            # stdin closed — process terminated externally
            return {"command": "terminate", "prompt_id": ""}
        try:
            return json.loads(line.strip())
        except json.JSONDecodeError:
            logger.warning(
                _("studio.command_parse_error", line=line.strip()[:80])
            )
            return {"command": "terminate", "prompt_id": ""}

    def send_prompt(
        self, kind: str, message: str, data: Optional[Dict[str, Any]] = None
    ) -> dict:
        """发送 prompt 事件并阻塞等待用户响应。

        Send a prompt event to stdout and block waiting for user response.
        这是 send_prompt + wait_for_command 的便捷组合。
        This is a convenience combination of emit("prompt") + wait_for_command().

        Args:
            kind:    prompt 类型 / Prompt kind: "api_clarification" | "plan_review".
            message: 提示消息（已翻译） / Prompt message (already translated).
            data:    附加数据 / Optional extra data (e.g. uncertainties, memory_dir).

        Returns:
            dict: 用户命令 / User command from studio.
        """
        prompt_id = self._next_prompt_id()
        logger.info(
            _("studio.prompt_sent", kind=kind, prompt_id=prompt_id)
        )
        self.emit(
            "prompt",
            id=prompt_id,
            kind=kind,
            message=message,
            data=data or {},
        )
        return self.wait_for_command()


# ============================================================================
# Studio 交互循环 / Studio interactive loop
# ============================================================================


def _extract_uncertainties(api_summary: list) -> list:
    """从 API 摘要中提取不确定性项以供 UI 展示。

    Extract uncertainty items from API summary for UI display.
    每项包含 api_path 和 issues 列表。
    Each item contains api_path and a list of issue field names.
    """
    items: list = []
    for item in api_summary:
        issues: list = []
        if item.get("auth_type") == "UNKNOWN":
            issues.append("auth_type")
        if item.get("need_token") is None:
            issues.append("need_token")
        description = item.get("description", "")
        if not description or description == "UNKNOWN":
            issues.append("description")
        if issues:
            api_path = f"{item.get('method', '?')} {item.get('api_path', item.get('path', '?'))}"
            items.append({"api_path": api_path, "issues": issues})
    return items


def _emit_log_for_agent(bridge: StudioBridge, level: str, message: str) -> None:
    """通过 bridge 发送 log 事件 / Send log event through bridge."""
    bridge.emit("log", level=level, message=message)


def run_studio_protocol(
    graph,
    initial: GraphState,
    config: dict,
    session_logger=None,
) -> GraphState:
    """在 Studio 模式下使用 JSON 协议运行 LangGraph 工作流。

    Run the LangGraph workflow in Studio mode using JSON protocol.
    替代 cli/interactive.py 的 run_interactive()。
    Replaces run_interactive() from cli/interactive.py.

    核心流程 / Core flow:
    1. 调用 graph.invoke() 启动流水线
    2. 捕获 GraphInterrupt → 发送 prompt 事件到 Studio
    3. 等待 Studio 返回 JSON 命令
    4. 根据命令类型恢复/修订/终止执行
    5. 循环直到所有节点完成
    """

    def _resume(value):
        """恢复图执行，捕获下一个 GraphInterrupt。

        Resume graph execution, catching the next GraphInterrupt.
        """
        try:
            return graph.invoke(Command(resume=value), config)
        except GraphInterrupt:
            return None

    bridge = StudioBridge()

    # 通知 Studio 已进入 studio 模式
    bridge.emit("log", level="info", message=_("studio.mode_enabled"))

    # 首次调用 — 可能直接抛出 GraphInterrupt
    # First invoke — may throw GraphInterrupt immediately
    try:
        result = graph.invoke(initial, config)
    except GraphInterrupt:
        result = None

    # 主循环：处理所有中断点 / Main loop: handle all interrupt points
    while True:
        snapshot = graph.get_state(config)
        if snapshot is None or not snapshot.next:
            break

        pending = snapshot.next[0] if snapshot.next else ""
        state_values = dict(snapshot.values) if snapshot.values else {}

        # ------------------------------------------------------------------
        # 中断点 1: API 分析确认 / analyze_api — clarification prompt
        # ------------------------------------------------------------------
        if pending == "analyze_api":
            api_summary = state_values.get("api_summary", [])
            uncertainties = _extract_uncertainties(api_summary)

            cmd = bridge.send_prompt(
                kind="api_clarification",
                message=_("review.prompt_clarify"),
                data={"uncertainties": uncertainties},
            )

            if cmd.get("command") == "skip":
                bridge.emit("log", level="info",
                            message=_("studio.clarification_skipped"))
                result = _resume("skip")
            elif cmd.get("command") == "respond":
                text = cmd.get("text", "")
                bridge.emit("log", level="info",
                            message=_("studio.clarification_response", text=text[:80]))
                result = _resume(text)
            elif cmd.get("command") == "terminate":
                bridge.emit("error", message=_("studio.terminated_by_user"))
                return state_values
            else:
                # 未知命令，默认 skip / Unknown command, default to skip
                bridge.emit("log", level="warn",
                            message=_("studio.unknown_command", cmd=str(cmd)))
                result = _resume("skip")

        # ------------------------------------------------------------------
        # 中断点 2: 测试计划审核 / human_confirm — plan review
        # ------------------------------------------------------------------
        elif pending == "human_confirm":
            memory_dir = state_values.get("memory_dir", "")
            plan_md = state_values.get("plan_md", "")

            cmd = bridge.send_prompt(
                kind="plan_review",
                message=_("review.interrupt_title"),
                data={
                    "memory_dir": memory_dir,
                    "plan_preview": plan_md[:1000] if plan_md else "",
                },
            )

            if cmd.get("command") == "approve":
                bridge.emit("log", level="info",
                            message=_("review.approved"))
                result = _resume("approved")

            elif cmd.get("command") == "revise_annotations":
                # 从磁盘读取 plan_comments.json（Studio 已写入）
                # Read plan_comments.json from disk (Studio has written it)
                from cli.interactive import _handle_annotation_revision

                success = _handle_annotation_revision(graph, config)
                if not success:
                    # 批注文件不存在或为空 → 返回 prompt 让用户重选
                    # Annotations file missing/empty → return to prompt
                    bridge.emit("log", level="warn",
                                message=_("review.annotations_not_found",
                                          path=str(Path(memory_dir) / "plan_comments.json")))
                    bridge.send_prompt(
                        kind="plan_review",
                        message=_("review.interrupt_title"),
                        data={
                            "memory_dir": memory_dir,
                            "plan_preview": plan_md[:1000] if plan_md else "",
                            "error": _("review.annotations_not_found_short"),
                        },
                    )
                    # 重新等待命令
                    # Re-prompt — this is a second prompt after the failed one
                    cmd2 = bridge.wait_for_command()
                    if cmd2.get("command") == "approve":
                        result = _resume("approved")
                    elif cmd2.get("command") == "revise_text":
                        from cli.interactive import _handle_text_revision
                        _handle_text_revision(graph, config, cmd2.get("text", ""))
                    elif cmd2.get("command") == "terminate":
                        bridge.emit("error", message=_("studio.terminated_by_user"))
                        return state_values
                    else:
                        result = _resume("approved")
                # result is set via graph.update_state in _handle_annotation_revision
                # The loop will re-enter human_confirm

            elif cmd.get("command") == "revise_text":
                from cli.interactive import _handle_text_revision
                feedback = cmd.get("text", "")
                if not feedback.strip():
                    bridge.emit("log", level="warn",
                                message=_("review.feedback_empty"))
                    continue  # Re-prompt
                _handle_text_revision(graph, config, feedback)
                # graph.update_state done, loop back to human_confirm

            elif cmd.get("command") == "terminate":
                bridge.emit("error", message=_("studio.terminated_by_user"))
                return state_values

            else:
                # 未知命令，默认 approve / Unknown command, default to approve
                bridge.emit("log", level="warn",
                            message=_("studio.unknown_command", cmd=str(cmd)))
                result = _resume("approved")

        else:
            # 不在中断点列表中的节点 → 退出循环
            # Node not in interrupt list → exit loop
            break

    # ------------------------------------------------------------------
    # 流水线完成 / Pipeline complete
    # ------------------------------------------------------------------
    final_state = dict(result or {})

    single_count = len(final_state.get("single_cases", []))
    biz_count = len(final_state.get("biz_flows", []))
    iface_count = len(final_state.get("interfaces", []))

    bridge.emit("complete", data={
        "single_cases": single_count,
        "biz_flows": biz_count,
        "interfaces": iface_count,
        "output_dir": final_state.get("output_dir", ""),
        "cases_dir": final_state.get("cases_dir", ""),
        "memory_dir": final_state.get("memory_dir", ""),
    })
    logger.info(
        _("studio.complete", single=single_count, biz=biz_count)
    )

    return final_state or {}
