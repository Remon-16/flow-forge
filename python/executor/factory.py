import importlib
from typing import Any, Dict

from executor.script_type import get_executor_class, get_biz_executor_class
from executor.base import BaseExecutor


class ExecutorFactory:
    """Creates the appropriate BaseExecutor subclass for a given script type."""

    @staticmethod
    def create(script_type: str, config: Dict[str, Any]) -> BaseExecutor:
        class_path = get_executor_class(script_type)
        return ExecutorFactory._instantiate(class_path, config)

    @staticmethod
    def create_biz(config: Dict[str, Any]) -> BaseExecutor:
        class_path = get_biz_executor_class()
        return ExecutorFactory._instantiate(class_path, config)

    @staticmethod
    def _instantiate(class_path: str, config: Dict[str, Any]) -> BaseExecutor:
        module_path, class_name = class_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        executor_cls = getattr(module, class_name)
        return executor_cls(config)
