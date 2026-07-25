"""插件加载器 — 从 PLUGIN_MODULES 配置加载插件。

Plugin loader: loads plugins from module paths configured in PLUGIN_MODULES.
"""

import importlib
import logging
from typing import List, Optional

from i18n import _
from plugins.base import CaseAttributeGenerator

logger = logging.getLogger(__name__)


def load_user_plugins(
    module_paths: List[str],
    settings=None,
    knowledge: Optional[object] = None,
) -> List[CaseAttributeGenerator]:
    """从 PLUGIN_MODULES 加载插件。

    Import and instantiate plugins from dotted module paths.
    Each path: "module.path.ClassName"

    Tries cls(settings, knowledge) first; falls back to cls() if
    the plugin constructor does not accept these arguments.

    Returns plugins in the order they appear in *module_paths*.
    """
    plugins: List[CaseAttributeGenerator] = []

    for path in module_paths:
        path = path.strip()
        if not path:
            continue

        if "." not in path:
            logger.warning(
                "Invalid plugin path (expected module.ClassName): %s", path
            )
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
            try:
                instance = cls(settings, knowledge)
            except TypeError:
                instance = cls()
            if not isinstance(instance, CaseAttributeGenerator):
                logger.warning(
                    "'%s' is not a CaseAttributeGenerator subclass", path
                )
                continue
            plugins.append(instance)
            logger.info(
                "Loaded plugin: %s (single=%s, biz=%s)",
                instance.declaration.plugin_name,
                instance.declaration.applies_to_single,
                instance.declaration.applies_to_biz,
            )
        except Exception:
            logger.exception("Failed to load plugin: %s", path)

    return plugins


def load_all_plugins(
    settings,
    knowledge: Optional[object] = None,
    user_module_paths: Optional[List[str]] = None,
    user_guidance: str = "",
) -> List[CaseAttributeGenerator]:
    """加载全部插件：从 PLUGIN_MODULES 配置的模块路径加载。

    Load all plugins from the module paths configured in PLUGIN_MODULES.
    Inject user_guidance into plugins that support it.
    """
    plugins = load_user_plugins(user_module_paths or [], settings, knowledge)

    # 检测插件加载不完整 / Detect incomplete plugin loading
    expected = len(user_module_paths or [])
    actual = len(plugins)
    if actual < expected:
        logger.error(
            _("batch_controller.plugins_partial_load",
              expected=expected, actual=actual, missing=expected - actual)
        )

    for p in plugins:
        if hasattr(p, "set_user_guidance"):
            p.set_user_guidance(user_guidance)

    names = [p.declaration.plugin_name for p in plugins]
    logger.info("All plugins loaded: %s", names)
    return plugins
