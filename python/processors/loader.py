"""Dynamic discovery of processor modules in the ``processors/`` directory."""

import importlib
import logging
import sys
from pathlib import Path
from processors.base import (
    _PRE_PROCESSOR_REGISTRY,
    _POST_PROCESSOR_REGISTRY,
)

logger = logging.getLogger(__name__)

_DISCOVERED = False


def discover_processors(processors_dir: Optional[str] = None) -> None:
    """Scan the processors directory and import all ``*.py`` modules.

    Modules are imported so that ``PreProcessor`` / ``PostProcessor``
    subclasses register themselves via ``__init_subclass__``.

    Idempotent — subsequent calls are no-ops.
    """
    global _DISCOVERED
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

    _DISCOVERED = True
    logger.info(
        "Processors discovered: %d pre, %d post",
        len(_PRE_PROCESSOR_REGISTRY),
        len(_POST_PROCESSOR_REGISTRY),
    )


