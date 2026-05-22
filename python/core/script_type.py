from enum import Enum


class ScriptType(str, Enum):
    API_TEST = "APITest"


_EXECUTOR_REGISTRY = {
    ScriptType.API_TEST: "executor.api_test.ApiTestExecutor",
}


def get_executor_class(script_type: str) -> str:
    """Look up the executor class path for a given script type.

    Returns the fully-qualified class path string.
    Raises ValueError if the script type is not registered.
    """
    if script_type not in _EXECUTOR_REGISTRY:
        known = list(_EXECUTOR_REGISTRY.keys())
        raise ValueError(f"Unknown script type: {script_type}. Known types: {known}")
    return _EXECUTOR_REGISTRY[script_type]
