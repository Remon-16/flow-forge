import importlib
from typing import Any, Dict

from core.script_type import get_executor_class
from executor.base import BaseExecutor


class ExecutorFactory:
    """Creates the appropriate BaseExecutor subclass for a given script type."""

    @staticmethod
    def create(script_type: str, config: Dict[str, Any]) -> BaseExecutor:
        class_path = get_executor_class(script_type)

        module_path, class_name = class_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        executor_cls = getattr(module, class_name)

        return executor_cls(config)
