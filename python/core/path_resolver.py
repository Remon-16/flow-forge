"""Shared utility for traversing nested dict/list structures with dot/bracket paths."""

import re
from typing import Any, List


class _Missing:
    """Sentinel indicating a field path could not be resolved."""


_SPLIT_RE = re.compile(r"[\.\[\]]")


def resolve_path(data: Any, path: str) -> Any:
    """Traverse a nested dict/list using dot-notation with optional bracket indices.

    Examples:
        'data.items.0.name'      -> data['data']['items'][0]['name']
        'data.records[0].id'     -> data['data']['records'][0]['id']
        '$.data.token'           -> data['data']['token']  ($. prefix stripped)
    """
    if not path:
        return _Missing()

    clean = path
    if clean.startswith("$."):
        clean = clean[2:]

    current = data
    for part in _SPLIT_RE.split(clean):
        if not part:
            continue
        if current is None:
            return _Missing()
        if isinstance(current, dict):
            if part in current:
                current = current[part]
            else:
                return _Missing()
        elif isinstance(current, list):
            try:
                idx = int(part)
                if 0 <= idx < len(current):
                    current = current[idx]
                else:
                    return _Missing()
            except (ValueError, IndexError):
                return _Missing()
        else:
            return _Missing()
    return current


def _split_parts(path: str) -> List[str]:
    """Split a path into parts, stripping $. prefix."""
    clean = path
    if clean.startswith("$."):
        clean = clean[2:]
    return [p for p in _SPLIT_RE.split(clean) if p]


def resolve_path_wildcard(data: Any, path: str) -> List[Any]:
    """Resolve a path that may contain [*] wildcards, collecting all matches.

    Example: 'data.list[*].price' -> [100, 200, 300]
    """
    parts = _split_parts(path)
    return _resolve_wildcard(data, parts)


def _resolve_wildcard(data: Any, parts: List[str]) -> List[Any]:
    if not parts:
        return [data]

    part = parts[0]
    rest = parts[1:]

    if part == "*":
        if not isinstance(data, list):
            return []
        results = []
        for item in data:
            results.extend(_resolve_wildcard(item, rest))
        return results

    if isinstance(data, dict):
        if part in data:
            return _resolve_wildcard(data[part], rest)
        return []
    elif isinstance(data, list):
        try:
            idx = int(part)
            if 0 <= idx < len(data):
                return _resolve_wildcard(data[idx], rest)
        except (ValueError, IndexError):
            pass
        return []
    return []


def resolve_length(data: Any, path: str) -> int:
    """Resolve a path ending with .length() and return len() of the result.

    Example: 'data.list.length()' -> 3
    """
    clean = path
    if clean.startswith("$."):
        clean = clean[2:]
    if clean.endswith(".length()"):
        clean = clean[:-len(".length()")]
    result = resolve_path(data, clean)
    if isinstance(result, _Missing):
        return -1
    if result is None:
        return 0
    if isinstance(result, (list, dict, str)):
        return len(result)
    return -1


def resolve_sum(data: Any, path: str) -> float:
    """Sum all values at a wildcard path.

    Example: 'data.list[*].price' -> sum of all price values
    """
    values = resolve_path_wildcard(data, path)
    try:
        return sum(float(v) for v in values)
    except (TypeError, ValueError):
        return 0.0


def resolve_sum_product(data: Any, path1: str, path2: str) -> float:
    """Sum of products of two wildcard paths.

    Example: path1='data.list[*].price', path2='data.list[*].count'
             -> sum(price_i * count_i)
    """
    values1 = resolve_path_wildcard(data, path1)
    values2 = resolve_path_wildcard(data, path2)
    if len(values1) != len(values2):
        return 0.0
    try:
        return sum(float(v1) * float(v2) for v1, v2 in zip(values1, values2))
    except (TypeError, ValueError):
        return 0.0
