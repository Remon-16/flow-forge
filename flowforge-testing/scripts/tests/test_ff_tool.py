"""ff_tool 子命令分发测试 — 全程 mock 子进程，不发起真实调用。

ff_tool subcommand dispatch tests: subprocesses are fully mocked.
"""

import os
import subprocess
import sys

import pytest

import ff_tool


class _FakeResult:
    """模拟 subprocess 返回结果。Fake subprocess result."""

    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_unknown_subcommand_exits_2():
    """未知子命令以退出码 2 结束。Unknown subcommand exits with code 2."""
    with pytest.raises(SystemExit) as exc:
        ff_tool.main(["bogus"])
    assert exc.value.code == 2


def test_execute_passes_through_args(monkeypatch, tmp_path, capsys):
    """execute 子命令透传执行器参数并返回其退出码。

    The execute subcommand passes executor args through and returns its code.
    """
    calls = {}

    def fake_run(cmd, **kwargs):
        calls["cmd"] = cmd
        calls["kwargs"] = kwargs
        return _FakeResult(0, '{"output": "report.html", "all_passed": true}\n', "")

    monkeypatch.setattr(ff_tool, "resolve_python", lambda config: sys.executable)
    monkeypatch.setattr(subprocess, "run", fake_run)
    cases = tmp_path / "cases"
    cases.mkdir()

    code = ff_tool.main(
        [
            "execute",
            "--yamlDir",
            str(cases),
            "--envName",
            "local",
            "--apiMode",
            "all",
            "--maxThread",
            "3",
        ]
    )
    assert code == 0
    assert calls["cmd"][0] == sys.executable
    assert calls["cmd"][1] == "main.py"
    assert "--yamlDir" in calls["cmd"]
    assert "--maxThread" in calls["cmd"]
    assert calls["kwargs"]["cwd"].endswith(os.path.join("python"))
    out = capsys.readouterr().out
    assert "report.html" in out


def test_execute_timeout_returns_124(monkeypatch, tmp_path):
    """超时终止后返回 124。Timeout terminates and returns 124."""

    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 0))

    monkeypatch.setattr(ff_tool, "resolve_python", lambda config: sys.executable)
    monkeypatch.setattr(subprocess, "run", fake_run)
    cases = tmp_path / "cases"
    cases.mkdir()
    code = ff_tool.main(
        ["execute", "--yamlDir", str(cases), "--timeout", "5"]
    )
    assert code == 124


def test_convert_yaml2excel_builds_command(monkeypatch, tmp_path):
    """convert yaml2excel 构造转换器命令。yaml2excel builds the converter command."""
    calls = {}

    def fake_run(cmd, **kwargs):
        calls["cmd"] = cmd
        return _FakeResult(0, "", "")

    monkeypatch.setattr(ff_tool, "resolve_python", lambda config: sys.executable)
    monkeypatch.setattr(subprocess, "run", fake_run)
    out = tmp_path / "cases.xlsx"
    code = ff_tool.main(
        [
            "convert",
            "yaml2excel",
            "--single-cases",
            str(tmp_path),
            "--output",
            str(out),
        ]
    )
    assert code == 0
    assert calls["cmd"][1] == "converter_main.py"
    assert "--single-cases" in calls["cmd"]
    assert "--output" in calls["cmd"]


def test_convert_excel2yaml_builds_command(monkeypatch, tmp_path):
    """convert excel2yaml 构造转换器命令。excel2yaml builds the converter command."""
    calls = {}

    def fake_run(cmd, **kwargs):
        calls["cmd"] = cmd
        return _FakeResult(0, "", "")

    monkeypatch.setattr(ff_tool, "resolve_python", lambda config: sys.executable)
    monkeypatch.setattr(subprocess, "run", fake_run)
    inp = tmp_path / "cases.xlsx"
    inp.write_bytes(b"not-a-real-xlsx")
    code = ff_tool.main(
        ["convert", "excel2yaml", "--input", str(inp), "--output", str(tmp_path)]
    )
    assert code == 0
    assert calls["cmd"][1] == "converter_main.py"
    assert "--input" in calls["cmd"]
    assert "--output" in calls["cmd"]
