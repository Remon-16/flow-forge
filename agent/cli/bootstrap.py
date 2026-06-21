"""CLI 引导 — 日志设置、会话目录和输出结构。

CLI bootstrap: logging setup, session directory, output structure.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Tuple


def setup_logging(verbose: bool = False) -> None:
    """配置日志级别和格式。

    Configure logging level and format.
    """
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(level=level, format=fmt, datefmt="%H:%M:%S")


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
