"""resolve_python 单元测试 — 覆盖解析优先级与缺配置回退。

Unit tests for resolve_python: resolution priority and fallbacks.
"""

import sys

import resolve_python as rp


def test_explicit_python_path_wins():
    """显式 python_path 优先。Explicit python_path wins."""
    cfg = {"python": {"python_path": sys.executable}}
    assert rp.resolve_python(cfg) == sys.executable


def test_explicit_invalid_path_falls_back_to_system():
    """无效 python_path 回退到 system 模式。Invalid python_path falls back."""
    cfg = {"python": {"python_path": "Z:/nonexistent/python.exe", "mode": "system"}}
    assert rp.resolve_python(cfg) == sys.executable


def test_system_mode_returns_current_interpreter():
    """system 模式返回当前解释器。System mode returns the current interpreter."""
    assert rp.resolve_python({"python": {"mode": "system"}}) == sys.executable


def test_empty_config_falls_back_to_system(monkeypatch):
    """空配置自动回退到当前解释器。Empty config falls back to the current one."""
    monkeypatch.setattr(rp, "_is_conda_available", lambda: False)
    assert rp.resolve_python({}) == sys.executable


def test_conda_env_resolution(monkeypatch):
    """conda 模式解析指定环境。Conda mode resolves the configured env."""
    fake = "C:/envs/api_test/python.exe"
    monkeypatch.setattr(rp, "_conda_env_python", lambda env: fake)
    cfg = {"python": {"mode": "conda", "conda_env": "api_test"}}
    assert rp.resolve_python(cfg) == fake


def test_conda_env_missing_falls_back(monkeypatch):
    """conda 环境不可用时回退。Unavailable conda env falls back."""
    monkeypatch.setattr(rp, "_conda_env_python", lambda env: "")
    monkeypatch.setattr(rp, "_find_venv_python", lambda root: "")
    cfg = {"python": {"mode": "conda", "conda_env": "nope"}}
    assert rp.resolve_python(cfg) == sys.executable


def test_venv_mode_finds_venv(monkeypatch, tmp_path):
    """venv 模式在仓库根目录发现解释器。Venv mode finds the interpreter."""
    venv_py = tmp_path / ".venv" / "Scripts" / "python.exe"
    venv_py.parent.mkdir(parents=True)
    venv_py.write_text("")
    cfg = {"flowforge_root": str(tmp_path), "python": {"mode": "venv"}}
    assert rp.resolve_python(cfg) == str(venv_py)


def test_check_deps_ok(monkeypatch):
    """依赖齐全时返回 True。Returns True when dependencies are present."""

    class _Res:
        returncode = 0

    monkeypatch.setattr(rp, "_run", lambda *a, **k: _Res())
    assert rp._check_deps("python") is True


def test_check_deps_missing(monkeypatch):
    """依赖缺失时返回 False。Returns False when dependencies are missing."""

    class _Res:
        returncode = 1

    monkeypatch.setattr(rp, "_run", lambda *a, **k: _Res())
    assert rp._check_deps("python") is False


def test_main_prints_python_and_exit_zero(monkeypatch, capsys):
    """CLI 输出解释器路径并以 0 退出。CLI prints the path and exits 0."""
    monkeypatch.setattr(rp, "_check_deps", lambda python: True)
    monkeypatch.setattr(rp, "_is_conda_available", lambda: False)
    code = rp.main(["--config", "Z:/nonexistent.yaml"])
    assert code == 0
    assert capsys.readouterr().out.strip() == sys.executable


def test_main_exit_one_when_deps_missing(monkeypatch, capsys):
    """依赖缺失时以 1 退出并仍输出路径。Exits 1 on missing deps, path still printed."""
    monkeypatch.setattr(rp, "_check_deps", lambda python: False)
    monkeypatch.setattr(rp, "_is_conda_available", lambda: False)
    code = rp.main(["--config", "Z:/nonexistent.yaml"])
    assert code == 1
    assert capsys.readouterr().out.strip() == sys.executable
