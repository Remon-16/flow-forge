"""插件加载器 — 统一加载默认插件和用户自定义插件。

Plugin loader: loads default plugins first, then user-configured plugins.
"""

import importlib
import logging
from typing import List, Optional

from plugins.base import CaseAttributeGenerator

logger = logging.getLogger(__name__)


def load_default_plugins(
    settings,
    knowledge: Optional[object] = None,
) -> List[CaseAttributeGenerator]:
    """加载默认插件（数据填充 + 断言生成）。

    Load the two default plugins: data filling and assertion generation.
    """
    from plugins.default import AssertionGenerationPlugin, DataFillingPlugin

    data = DataFillingPlugin(settings, knowledge)
    assertion = AssertionGenerationPlugin(settings, knowledge)
    logger.info(
        "Loaded default plugins: data_filling, assertion_generation"
    )
    return [data, assertion]


def load_user_plugins(
    module_paths: List[str],
) -> List[CaseAttributeGenerator]:
    """从 PLUGIN_MODULES 加载用户自定义插件。

    Import and instantiate plugins from dotted module paths.
    Each path: "module.path.ClassName"

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
    """加载全部插件：默认插件 + 用户插件。

    Load all plugins: defaults first, then user-specified.
    用户可通过 PLUGIN_MODULES 覆盖默认插件（同名跳过默认）。
    """
    default_plugins = load_default_plugins(settings, knowledge)
    user_plugins = load_user_plugins(user_module_paths or [])

    # 用户显式指定的插件取代同功能默认插件
    # If user specifies a plugin with the same name as a default, skip the default
    user_names = {p.declaration.plugin_name for p in user_plugins}
    all_plugins = [
        p for p in default_plugins if p.declaration.plugin_name not in user_names
    ] + user_plugins

    # 注入用户指导
    # Inject user guidance into plugins that support it
    for p in all_plugins:
        if hasattr(p, "set_user_guidance"):
            p.set_user_guidance(user_guidance)

    names = [p.declaration.plugin_name for p in all_plugins]
    logger.info("All plugins loaded: %s", names)
    return all_plugins
