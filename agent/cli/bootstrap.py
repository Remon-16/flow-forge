"""CLI 引导 — 日志设置、会话目录和输出结构。

CLI bootstrap: logging setup, session directory, output structure.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Tuple

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False) -> None:
    """Phase 1: 配置控制台日志级别和格式。

    Configure console logging level and format.
    """
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(level=level, format=fmt, datefmt="%H:%M:%S")


def setup_file_logging(output_dir: str) -> None:
    """Phase 2: 添加文件日志 handler，将日志持久化到 {output_dir}/logs/agent.log。

    Add a FileHandler to persist logs to {output_dir}/logs/agent.log.
    Duplicate calls are safe (no-op when already configured).

    文件日志级别跟随控制台设置（--debug 时 DEBUG，否则 INFO）。
    File log level follows the console level (DEBUG with --debug, else INFO).
    """
    log_dir = Path(output_dir) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "agent.log"

    root = logging.getLogger()
    target_path = str(log_file.resolve())

    # 防止重复添加 / Avoid duplicate handlers
    for h in root.handlers:
        if isinstance(h, logging.FileHandler) and h.baseFilename == target_path:
            return

    handler = logging.FileHandler(str(log_file), encoding="utf-8")
    handler.setLevel(root.level)
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    handler.setFormatter(logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S"))
    root.addHandler(handler)
    logger.info("File logging enabled: %s", log_file)


def make_session_dir() -> Path:
    """在 logs/ 下创建时间戳会话目录。

    Create a timestamped session directory under logs/.
    """
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    session_dir = Path("logs") / ts
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def ensure_output_structure(output_dir: Path) -> Tuple[Path, Path]:
    """创建输出目录结构。

    Create the output directory structure. Returns (cases_dir, memory_dir).
    """
    cases_dir = output_dir / "cases"
    memory_dir = output_dir / "memory"
    snapshots_dir = memory_dir / "snapshots"

    for d in [
        cases_dir / "interfaces",
        cases_dir / "single_cases",
        cases_dir / "biz_flows",
        snapshots_dir,
    ]:
        d.mkdir(parents=True, exist_ok=True)

    return cases_dir, memory_dir
