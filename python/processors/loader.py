"""Dynamic discovery of processor modules in the ``processors/`` directory."""

import importlib
import logging
import sys
import threading
from pathlib import Path
from typing import Optional

from processors.base import (
    _PRE_PROCESSOR_REGISTRY,
    _POST_PROCESSOR_REGISTRY,
)

logger = logging.getLogger(__name__)

_DISCOVERED = False
_DISCOVERY_LOCK = threading.Lock()
"""锁保护 _DISCOVERED 的读写，防止多线程并发发现的 TOCTOU 竞态。
Lock guarding _DISCOVERED read/write to prevent TOCTOU race during concurrent discovery."""


def discover_processors(processors_dir: Optional[str] = None) -> None:
    """Scan the processors directory and import all ``*.py`` modules.

    Modules are imported so that ``PreProcessor`` / ``PostProcessor``
    subclasses register themselves via ``__init_subclass__``.

    Also loads the ``processors.builtin`` package which contains the
    official built-in processors.

    Idempotent — subsequent calls are no-ops.
    """
    global _DISCOVERED
    # 快速路径：已发现则直接返回，不获取锁，避免性能开销
    # Fast path: return immediately if already discovered, avoid lock overhead
    if _DISCOVERED:
        return

    with _DISCOVERY_LOCK:
        # 双重检查：持有锁后再次确认，防止多个线程同时通过快速路径
        # Double check under lock: re-confirm to prevent multiple threads passing the fast path
        if _DISCOVERED:
            return

        if processors_dir is None:
            # Default: processors/ directory next to this file
            processors_dir = str(Path(__file__).resolve().parent)

        root = Path(processors_dir)
        if not root.is_dir():
            logger.debug("Processors directory not found: %s", root)
            _DISCOVERED = True
            return

        for py_file in sorted(root.glob("*.py")):
            module_name = py_file.stem
            if module_name.startswith("_") or module_name in ("base", "loader", "runner"):
                continue

            # Build a dotted module name relative to cwd
            try:
                rel = py_file.relative_to(Path.cwd())
            except ValueError:
                rel = py_file.resolve().relative_to(Path.cwd())

            dotted = str(rel.with_suffix("")).replace("\\", "/").replace("/", ".")
            logger.debug("Discovering processor module: %s", dotted)

            try:
                importlib.import_module(dotted)
            except Exception:
                logger.warning("Failed to import processor module %s", dotted, exc_info=True)

        # Load built-in processors shipped with the framework
        try:
            importlib.import_module("processors.builtin")
        except Exception:
            logger.debug("Built-in processors not available", exc_info=True)

        _DISCOVERED = True
        logger.info(
            "Processors discovered: %d pre, %d post",
            len(_PRE_PROCESSOR_REGISTRY),
            len(_POST_PROCESSOR_REGISTRY),
        )
