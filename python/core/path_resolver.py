"""Shared utility for traversing nested dict/list structures with dot/bracket paths."""

import re
from typing import Any


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
