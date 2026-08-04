"""解析 Python 解释器 — 根据 flowforge.config.yaml 解析可用的 Python 可执行路径。

Resolve the Python interpreter executable from flowforge.config.yaml.

解析优先级 / Resolution priority:
    python_path (显式 / explicit) > mode (conda/venv/system) > auto detection
输出到 stdout 的是可执行文件的绝对路径，可直接用于后续子进程调用。
The absolute path of the resolved executable is printed to stdout so
downstream subprocess calls can use it directly.
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
import sys
import os
from pathlib import Path
from typing import Optional

import yaml

# 注入 scripts 目录，使 i18n 可导入 / Inject the scripts dir so i18n is importable
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from i18n import _, set_lang  # noqa: E402

logger = logging.getLogger(__name__)

# 执行器/转换器所需的 Python 依赖 / Python dependencies needed by executor/converter
REQUIRED_MODULES = ("requests", "openpyxl", "yaml")

DEFAULT_CONFIG_NAME = "flowforge.config.yaml"


def find_skill_root() -> Path:
    """定位 skill 根目录。Locate the skill root directory."""
    return Path(__file__).resolve().parent.parent


def find_config_file(explicit: str = "") -> Optional[Path]:
    """查找配置文件：--config 显式指定 > skill 目录 > 当前目录。

    Locate the config file: explicit --config > skill dir > CWD.
    """
    if explicit:
        p = Path(explicit)
        if p.is_file():
            return p
    for candidate in (find_skill_root() / DEFAULT_CONFIG_NAME, Path.cwd() / DEFAULT_CONFIG_NAME):
        if candidate.is_file():
            return candidate
    return None


def load_config(explicit: str = "") -> dict:
    """加载配置，文件缺失时返回空字典。

    Load the config; return an empty dict when the file is missing.
    """
    cfg_path = find_config_file(explicit)
    if cfg_path is None:
        logger.warning(_("tool.config_not_found", path=DEFAULT_CONFIG_NAME))
        return {}
    logger.info(_("tool.config_loaded", path=str(cfg_path)))
    with open(cfg_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _run(cmd, timeout: int = 30) -> subprocess.CompletedProcess:
    """执行子进程并返回结果，避免阻塞主线程。

    Run a subprocess with a timeout and return the result.
    """
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _is_conda_available() -> bool:
    """检测 conda 命令是否可用。Check whether the conda command is available."""
    return shutil.which("conda") is not None


def _conda_env_python(conda_env: str) -> str:
    """返回 conda 环境的 Python 可执行路径，不可用时返回空串。

    Return the Python executable path inside a conda environment, or an
    empty string when unavailable. Uses ``conda env list --json`` instead of
    ``conda run`` so the resolution never blocks on a hanging child process.
    """
    if not conda_env or not _is_conda_available():
        return ""
    try:
        res = _run(["conda", "env", "list", "--json"], timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if res.returncode != 0:
        logger.warning(_("tool.conda_env_missing", env=conda_env))
        return ""
    try:
        data = json.loads(res.stdout)
    except json.JSONDecodeError:
        return ""
    exe_name = "python.exe" if os.name == "nt" else "bin/python"
    for env_path in data.get("envs", []):
        if Path(env_path).name == conda_env:
            exe = Path(env_path) / exe_name
            if exe.is_file():
                return str(exe)
    return ""


def _find_venv_python(root: Path) -> str:
    """在仓库根目录查找常见 venv 布局的解释器。

    Look for a Python interpreter in common venv layouts under *root*.
    """
    candidates = (
        Path(".venv/Scripts/python.exe"),
        Path(".venv/bin/python"),
        Path("venv/Scripts/python.exe"),
        Path("venv/bin/python"),
    )
    for rel in candidates:
        p = root / rel
        if p.is_file():
            return str(p)
    return ""


def _check_deps(python: str) -> bool:
    """检查目标环境能否导入执行器所需的模块。

    Check that the target environment can import the modules required by
    the executor and converter.
    """
    import_line = ";".join(f"import {m}" for m in REQUIRED_MODULES)
    try:
        res = _run([python, "-c", import_line])
    except (OSError, subprocess.TimeoutExpired):
        return False
    return res.returncode == 0


def resolve_python(config: dict) -> str:
    """按优先级解析 Python 可执行路径。

    Resolve the Python executable path by priority:
    python_path -> explicit mode (conda/venv/system) -> auto detection.
    """
    python_cfg = config.get("python") or {}
    root = Path(str(config.get("flowforge_root") or "").strip() or find_skill_root().parent)

    # 1) 显式解释器路径 / Explicit interpreter path
    explicit = str(python_cfg.get("python_path") or "").strip()
    if explicit:
        if Path(explicit).is_file():
            return explicit
        logger.warning(_("tool.python_path_invalid", path=explicit))

    # 2) 显式模式 / Explicit mode
    mode = str(python_cfg.get("mode") or "auto").strip().lower()
    if mode == "conda":
        env = str(python_cfg.get("conda_env") or "").strip()
        path = _conda_env_python(env)
        if path:
            return path
        logger.warning(_("tool.conda_env_missing", env=env or "(none)"))
    elif mode == "venv":
        venv_path = str(python_cfg.get("venv_path") or "").strip()
        if venv_path and Path(venv_path).is_file():
            return venv_path
        found = _find_venv_python(root)
        if found:
            return found
        logger.warning(_("tool.venv_not_found"))
    elif mode == "system":
        return sys.executable

    # 3) 自动探测：conda 环境 > venv > 当前解释器 / Auto: conda env > venv > current
    env = str(python_cfg.get("conda_env") or "").strip()
    if env:
        path = _conda_env_python(env)
        if path:
            return path
    found = _find_venv_python(root)
    if found:
        return found
    return sys.executable


def main(argv=None) -> int:
    """CLI 入口：输出解析到的解释器路径并检查依赖。

    CLI entry: print the resolved interpreter path and check dependencies.
    Exit codes: 0 resolved with dependencies OK; 1 resolved but deps
    missing; 2 resolution failed.
    """
    parser = argparse.ArgumentParser(
        description="Resolve the Flow Forge Python interpreter."
    )
    parser.add_argument(
        "--config",
        default="",
        help="Path to flowforge.config.yaml (optional)",
    )
    args = parser.parse_args(argv)

    config = load_config(args.config)
    set_lang(str(config.get("language") or "zh_CN"))
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    logger.info(_("tool.resolving_python"))
    python = resolve_python(config)
    if not python:
        logger.error(_("tool.python_not_found"))
        return 2
    print(python)
    logger.info(_("tool.resolved_python", path=python))

    if not _check_deps(python):
        logger.warning(_("tool.deps_missing", deps=", ".join(REQUIRED_MODULES)))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
