"""StudioBridge 单元测试。

StudioBridge unit tests. All tests use mock stdin/stdout — no real
subprocess communication or LLM calls.
"""

import io
import json
import sys

import pytest

from cli.studio_bridge import StudioBridge, _extract_uncertainties


# ============================================================================
# 测试辅助 / Test helpers
# ============================================================================


class _MockStdin:
    """模拟 stdin 用于测试 / Mock stdin for testing."""

    def __init__(self, lines):
        self._lines = lines
        self._idx = 0

    def readline(self):
        if self._idx < len(self._lines):
            line = self._lines[self._idx]
            self._idx += 1
            return line
        return ""  # EOF


def _setup_bridge(stdin_lines=None):
    """创建 StudioBridge 并重定向 stdout/stdin 进行测试。

    Create a StudioBridge and redirect stdout/stdin for testing.
    Returns (bridge, stdout_io).
    """
    if stdin_lines is None:
        stdin_lines = []
    bridge = StudioBridge()
    stdout_io = io.StringIO()
    # Save originals
    _orig_stdout = sys.stdout
    _orig_stdin = sys.stdin
    sys.stdout = stdout_io
    sys.stdin = _MockStdin(stdin_lines)
    # Return cleanup info
    return bridge, stdout_io, _orig_stdout, _orig_stdin


def _teardown_bridge(orig_stdout, orig_stdin):
    """恢复 stdout/stdin / Restore stdout/stdin."""
    sys.stdout = orig_stdout
    sys.stdin = orig_stdin


def _read_events(stdout_io):
    """从捕获的 stdout 读取所有 JSON 事件 / Read all JSON events from captured stdout."""
    stdout_io.seek(0)
    events = []
    for line in stdout_io:
        line = line.strip()
        if line:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return events


# ============================================================================
# TestStudioBridge: 基础协议测试 / Basic protocol tests
# ============================================================================


class TestStudioBridgeEmit:
    """emit() 方法测试 / emit() method tests."""

    def test_emit_single_event(self):
        """emit 写入一行完整 JSON 事件到 stdout。

        emit writes one complete JSON event line to stdout.
        """
        bridge, stdout_io, orig_out, orig_in = _setup_bridge()
        try:
            bridge.emit("log", level="info", message="Hello World")
            events = _read_events(stdout_io)
            assert len(events) == 1
            assert events[0]["type"] == "log"
            assert events[0]["level"] == "info"
            assert events[0]["message"] == "Hello World"
            assert "ts" in events[0]
        finally:
            _teardown_bridge(orig_out, orig_in)

    def test_emit_multiple_events(self):
        """emit 多次写入多行 JSON，每行一个事件。

        emit writes multiple JSON lines, one event per line.
        """
        bridge, stdout_io, orig_out, orig_in = _setup_bridge()
        try:
            bridge.emit("log", level="info", message="Event 1")
            bridge.emit("progress", stage="analyze_api", step="2/10")
            bridge.emit("log", level="warn", message="Event 3")
            events = _read_events(stdout_io)
            assert len(events) == 3
            assert events[0]["type"] == "log"
            assert events[1]["type"] == "progress"
            assert events[2]["type"] == "log"
        finally:
            _teardown_bridge(orig_out, orig_in)

    def test_emit_unicode_message(self):
        """emit 正确处理包含中文的 Unicode 消息。

        emit correctly handles Unicode messages with Chinese characters.
        """
        bridge, stdout_io, orig_out, orig_in = _setup_bridge()
        try:
            bridge.emit("log", level="info", message="骨架批次 1/3: 已生成 10/30")
            events = _read_events(stdout_io)
            assert len(events) == 1
            assert "骨架批次 1/3" in events[0]["message"]
            assert events[0]["message"] == "骨架批次 1/3: 已生成 10/30"
        finally:
            _teardown_bridge(orig_out, orig_in)

    def test_emit_complete_event(self):
        """emit 正确序列化嵌套 data 对象到 complete 事件。

        emit correctly serializes nested data object in complete event.
        """
        bridge, stdout_io, orig_out, orig_in = _setup_bridge()
        try:
            bridge.emit("complete", data={
                "single_cases": 50,
                "biz_flows": 3,
                "interfaces": 12,
            })
            events = _read_events(stdout_io)
            assert len(events) == 1
            assert events[0]["type"] == "complete"
            assert events[0]["data"]["single_cases"] == 50
            assert events[0]["data"]["biz_flows"] == 3
        finally:
            _teardown_bridge(orig_out, orig_in)

    def test_emit_prompt_event_with_id(self):
        """emit prompt 事件包含递增 id。

        emit prompt event includes incrementing id.
        """
        bridge, stdout_io, orig_out, orig_in = _setup_bridge()
        try:
            bridge.emit("prompt", id="p1", kind="api_clarification",
                        message="test", data={})
            bridge.emit("prompt", id="p2", kind="plan_review",
                        message="test2", data={})
            events = _read_events(stdout_io)
            assert events[0]["id"] == "p1"
            assert events[1]["id"] == "p2"
        finally:
            _teardown_bridge(orig_out, orig_in)


class TestStudioBridgeWaitForCommand:
    """wait_for_command() 方法测试 / wait_for_command() method tests."""

    def test_read_skip_command(self):
        """wait_for_command 读取 skip 命令 JSON。

        wait_for_command reads a skip command JSON.
        """
        line = json.dumps({"command": "skip", "prompt_id": "p1"}) + "\n"
        bridge, stdout_io, orig_out, orig_in = _setup_bridge([line])
        try:
            cmd = bridge.wait_for_command()
            assert cmd["command"] == "skip"
            assert cmd["prompt_id"] == "p1"
        finally:
            _teardown_bridge(orig_out, orig_in)

    def test_read_respond_command(self):
        """wait_for_command 读取 respond 命令 JSON。

        wait_for_command reads a respond command JSON.
        """
        line = json.dumps({
            "command": "respond",
            "prompt_id": "p3",
            "text": "Use JWT auth",
        }) + "\n"
        bridge, stdout_io, orig_out, orig_in = _setup_bridge([line])
        try:
            cmd = bridge.wait_for_command()
            assert cmd["command"] == "respond"
            assert cmd["text"] == "Use JWT auth"
        finally:
            _teardown_bridge(orig_out, orig_in)

    def test_read_approve_command(self):
        """wait_for_command 读取 approve 命令 JSON。

        wait_for_command reads an approve command JSON.
        """
        line = json.dumps({"command": "approve", "prompt_id": "p2"}) + "\n"
        bridge, stdout_io, orig_out, orig_in = _setup_bridge([line])
        try:
            cmd = bridge.wait_for_command()
            assert cmd["command"] == "approve"
        finally:
            _teardown_bridge(orig_out, orig_in)

    def test_read_revise_annotations_command(self):
        """wait_for_command 读取 revise_annotations 命令 JSON。

        wait_for_command reads a revise_annotations command JSON.
        """
        line = json.dumps({
            "command": "revise_annotations",
            "prompt_id": "p5",
        }) + "\n"
        bridge, stdout_io, orig_out, orig_in = _setup_bridge([line])
        try:
            cmd = bridge.wait_for_command()
            assert cmd["command"] == "revise_annotations"
        finally:
            _teardown_bridge(orig_out, orig_in)

    def test_read_revise_text_command(self):
        """wait_for_command 读取 revise_text 命令 JSON。

        wait_for_command reads a revise_text command JSON.
        """
        line = json.dumps({
            "command": "revise_text",
            "prompt_id": "p4",
            "text": "Change the plan structure",
        }) + "\n"
        bridge, stdout_io, orig_out, orig_in = _setup_bridge([line])
        try:
            cmd = bridge.wait_for_command()
            assert cmd["command"] == "revise_text"
            assert cmd["text"] == "Change the plan structure"
        finally:
            _teardown_bridge(orig_out, orig_in)

    def test_read_terminate_command(self):
        """wait_for_command 读取 terminate 命令 JSON。

        wait_for_command reads a terminate command JSON.
        """
        line = json.dumps({"command": "terminate", "prompt_id": ""}) + "\n"
        bridge, stdout_io, orig_out, orig_in = _setup_bridge([line])
        try:
            cmd = bridge.wait_for_command()
            assert cmd["command"] == "terminate"
        finally:
            _teardown_bridge(orig_out, orig_in)

    def test_eof_returns_terminate(self):
        """stdin EOF 时 wait_for_command 返回 terminate 命令。

        wait_for_command returns terminate command on stdin EOF.
        """
        bridge, stdout_io, orig_out, orig_in = _setup_bridge([])
        try:
            cmd = bridge.wait_for_command()
            assert cmd["command"] == "terminate"
        finally:
            _teardown_bridge(orig_out, orig_in)

    def test_invalid_json_returns_terminate(self):
        """wait_for_command 在无效 JSON 时返回 terminate 命令。

        wait_for_command returns terminate on invalid JSON.
        """
        bridge, stdout_io, orig_out, orig_in = _setup_bridge(["not valid json\n"])
        try:
            cmd = bridge.wait_for_command()
            assert cmd["command"] == "terminate"
        finally:
            _teardown_bridge(orig_out, orig_in)


class TestStudioBridgeSendPrompt:
    """send_prompt() 方法测试 / send_prompt() method tests."""

    def test_send_prompt_emits_and_waits(self):
        """send_prompt 先发 prompt 事件，再等待命令响应。

        send_prompt emits prompt event then waits for command response.
        """
        line = json.dumps({"command": "skip", "prompt_id": "p1"}) + "\n"
        bridge, stdout_io, orig_out, orig_in = _setup_bridge([line])
        try:
            cmd = bridge.send_prompt(
                kind="api_clarification",
                message="Please clarify",
                data={"uncertainties": []},
            )
            events = _read_events(stdout_io)
            # 验证 prompt 事件已发送 / Verify prompt event was sent
            assert len(events) == 1
            assert events[0]["type"] == "prompt"
            assert events[0]["kind"] == "api_clarification"
            assert events[0]["message"] == "Please clarify"
            assert events[0]["id"] == "p1"
            # 验证响应已读取 / Verify response was read
            assert cmd["command"] == "skip"
        finally:
            _teardown_bridge(orig_out, orig_in)

    def test_send_prompt_ids_increment(self):
        """每次 send_prompt 使用递增的 prompt_id。

        Each send_prompt uses an incrementing prompt_id.
        """
        line1 = json.dumps({"command": "skip", "prompt_id": "p1"}) + "\n"
        line2 = json.dumps({"command": "approve", "prompt_id": "p2"}) + "\n"
        bridge, stdout_io, orig_out, orig_in = _setup_bridge([line1, line2])
        try:
            bridge.send_prompt("api_clarification", "Q1")
            bridge.send_prompt("plan_review", "Q2")
            events = _read_events(stdout_io)
            assert events[0]["id"] == "p1"
            assert events[1]["id"] == "p2"
        finally:
            _teardown_bridge(orig_out, orig_in)

    def test_send_prompt_plan_review(self):
        """send_prompt 正确处理 plan_review 类型的 prompt。

        send_prompt correctly handles plan_review prompt kind.
        """
        line = json.dumps({
            "command": "approve",
            "prompt_id": "p1",
        }) + "\n"
        bridge, stdout_io, orig_out, orig_in = _setup_bridge([line])
        try:
            cmd = bridge.send_prompt(
                kind="plan_review",
                message="Review the test plan",
                data={"memory_dir": "/tmp/memory", "plan_preview": "# Plan..."},
            )
            events = _read_events(stdout_io)
            assert events[0]["kind"] == "plan_review"
            assert events[0]["data"]["memory_dir"] == "/tmp/memory"
            assert cmd["command"] == "approve"
        finally:
            _teardown_bridge(orig_out, orig_in)


# ============================================================================
# TestExtractUncertainties: 不确定性提取 / Uncertainty extraction
# ============================================================================


class TestExtractUncertainties:
    """_extract_uncertainties() 函数测试."""

    def test_extract_with_auth_unknown(self):
        """提取 auth_type=UNKNOWN 的不确定性。

        Extract uncertainty when auth_type is UNKNOWN.
        """
        summary = [{"auth_type": "UNKNOWN", "need_token": True,
                     "description": "Login API", "method": "POST",
                     "api_path": "/api/login"}]
        items = _extract_uncertainties(summary)
        assert len(items) == 1
        assert "auth_type" in items[0]["issues"]

    def test_extract_with_multiple_issues(self):
        """同一接口多个不确定性全部提取。

        Multiple issues on the same API are all extracted.
        """
        summary = [{"auth_type": "UNKNOWN", "need_token": None,
                     "description": "UNKNOWN", "method": "GET",
                     "api_path": "/api/users"}]
        items = _extract_uncertainties(summary)
        assert len(items) == 1
        assert len(items[0]["issues"]) == 3  # auth_type, need_token, description

    def test_extract_with_no_uncertainties(self):
        """无不确定性时返回空列表。

        Returns empty list when no uncertainties.
        """
        summary = [{"auth_type": "JWT", "need_token": True,
                     "description": "Get users", "method": "GET",
                     "api_path": "/api/users"}]
        items = _extract_uncertainties(summary)
        assert len(items) == 0

    def test_extract_with_empty_summary(self):
        """空 summary 返回空列表。

        Empty summary returns empty list.
        """
        items = _extract_uncertainties([])
        assert len(items) == 0

    def test_extract_uses_api_path_field(self):
        """正确使用 api_path 字段（备选 path 字段）。

        Correctly uses api_path field with path fallback.
        """
        summary = [{"auth_type": "UNKNOWN", "need_token": True,
                     "description": "test", "method": "DELETE",
                     "path": "/api/items"}]
        items = _extract_uncertainties(summary)
        assert len(items) == 1
        assert "/api/items" in items[0]["api_path"]
