from enum import Enum


class ScriptType(str, Enum):
    API_TEST = "APITest"


_EXECUTOR_REGISTRY = {
    ScriptType.API_TEST: "executor.single_case.SingleCaseExecutor",
}

_BIZ_EXECUTOR_CLASS = "executor.biz_flow.BizFlowExecutor"


def get_executor_class(script_type: str) -> str:
    if script_type not in _EXECUTOR_REGISTRY:
        known = list(_EXECUTOR_REGISTRY.keys())
        raise ValueError(f"Unknown script type: {script_type}. Known types: {known}")
    return _EXECUTOR_REGISTRY[script_type]


def get_biz_executor_class() -> str:
    return _BIZ_EXECUTOR_CLASS
