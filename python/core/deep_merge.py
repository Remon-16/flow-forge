from copy import deepcopy
from typing import Any, Dict


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge two dicts.

    Keys present in both dicts where both values are dicts are merged recursively.
    For non-dict values, the override value wins.
    Keys only in base are preserved; keys only in override are added.

    Returns a new dict — neither input is mutated.
    """
    if base is None:
        return deepcopy(override) if override is not None else {}
    if override is None:
        return deepcopy(base)

    result = deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result
