"""ToolRegistry — decorator-based tool registration with auto-discovery."""

import importlib
import logging
import pkgutil
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .base import BaseTool

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Global registry for tools accessible by ReAct agents.

    Tools are registered via the ``@ToolRegistry.register()`` decorator
    or discovered automatically from ``tools/builtin/`` and
    ``tools/custom/``.
    """

    _tools: Dict[str, BaseTool] = {}

    # ------------------------------------------------------------------
    # Decorator
    # ------------------------------------------------------------------
    @classmethod
    def register(
        cls,
        name: Optional[str] = None,
        description: str = "",
        parameters: Optional[Dict] = None,
    ):
        """Decorator that registers a function as a tool.

        Usage::

            @ToolRegistry.register(name="execute_sql", description="Run SQL")
            def execute_sql(query: str) -> list[dict]: ...
        """

        def decorator(func: Callable):
            tool_name = name or func.__name__
            cls._tools[tool_name] = BaseTool(
                name=tool_name,
                description=description or (func.__doc__ or "").strip(),
                func=func,
                parameters=parameters or {},
            )
            logger.debug("Registered tool: %s", tool_name)
            return func

        return decorator

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------
    @classmethod
    def get(cls, name: str) -> Optional[BaseTool]:
        return cls._tools.get(name)

    @classmethod
    def get_all(cls) -> Dict[str, BaseTool]:
        return dict(cls._tools)

    @classmethod
    def get_many(cls, names: List[str]) -> List[BaseTool]:
        """Return tools for the given names, skipping unknown names."""
        tools = []
        for n in names:
            t = cls._tools.get(n)
            if t:
                tools.append(t)
            else:
                logger.warning("Tool '%s' requested but not registered", n)
        return tools

    @classmethod
    def list_names(cls) -> List[str]:
        return sorted(cls._tools.keys())

    # ------------------------------------------------------------------
    # Auto-discovery
    # ------------------------------------------------------------------
    @classmethod
    def auto_discover(cls, package_path: str = "tools.builtin"):
        """Import all modules under *package_path* so decorators fire.

        Call once at startup::

            ToolRegistry.auto_discover("tools.builtin")
            ToolRegistry.auto_discover("tools.custom")
        """
        try:
            pkg = importlib.import_module(package_path)
            pkg_dir = Path(pkg.__path__[0])
            for _, mod_name, _ in pkgutil.iter_modules([str(pkg_dir)]):
                full_name = f"{package_path}.{mod_name}"
                importlib.import_module(full_name)
                logger.debug("Auto-discovered tool module: %s", full_name)
        except ModuleNotFoundError:
            logger.debug("Tool package '%s' not found, skipping.", package_path)

    @classmethod
    def clear(cls):
        """Remove all registered tools (mainly for testing)."""
        cls._tools.clear()
