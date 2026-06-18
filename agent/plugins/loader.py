"""Dynamic import of plugin modules from dotted paths."""

import importlib
import logging
from typing import List

from plugins.base import CaseAttributeGenerator

logger = logging.getLogger(__name__)


def load_plugins(module_paths: List[str]) -> List[CaseAttributeGenerator]:
    """Import and instantiate plugins from a list of dotted module paths.

    Each path should point to a class that subclasses
    :class:`CaseAttributeGenerator`, e.g.::

        "my_plugins.single_pre_processor.SinglePreProcessor"

    Plugins are returned in the order they appear in *module_paths*.
    """
    plugins: List[CaseAttributeGenerator] = []

    for path in module_paths:
        path = path.strip()
        if not path:
            continue

        if "." not in path:
            logger.warning("Invalid plugin path (expected module.ClassName): %s", path)
            continue

        module_path, class_name = path.rsplit(".", 1)
        try:
            module = importlib.import_module(module_path)
            cls = getattr(module, class_name, None)
            if cls is None:
                logger.warning(
                    "Class '%s' not found in module '%s'", class_name, module_path
                )
                continue
            instance = cls()
            if not isinstance(instance, CaseAttributeGenerator):
                logger.warning(
                    "'%s' is not a CaseAttributeGenerator subclass", path
                )
                continue
            plugins.append(instance)
            logger.info(
                "Loaded plugin: %s (applies_single=%s, applies_biz=%s)",
                instance.declaration.plugin_name,
                instance.declaration.applies_to_single,
                instance.declaration.applies_to_biz,
            )
        except Exception:
            logger.exception("Failed to load plugin: %s", path)

    return plugins
