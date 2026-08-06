import re
from typing import Callable, Optional

# 仅匹配单词字符（字母、数字、下划线），避免误匹配 JSON 花括号和模板语法
# Only match word characters (letters, digits, underscores) to avoid
# false matches against JSON curly braces and template syntax
_VAR_PATTERN = re.compile(r"#\{(\w+)\}")
_CURLY_PATTERN = re.compile(r"\{(\w+)\}")


def resolve_placeholders(
    text: str,
    resolver: Callable[[str], Optional[str]],
) -> str:
    """Replace all #{varName} placeholders in a string.

    Calls ``resolver(varName)`` for each placeholder. If the resolver returns
    a non-None value, the placeholder is replaced; otherwise it is left as-is.

    Supports embedded placeholders such as ``"Bearer #{token}"`` — the
    placeholder does not need to be the entire string.
    """
    def replacer(match: re.Match) -> str:
        var_name = match.group(1)
        value = resolver(var_name)
        if value is not None:
            return value
        return match.group(0)

    return _VAR_PATTERN.sub(replacer, text)


def has_placeholders(text: str) -> bool:
    """Return True if the string contains at least one #{varName} placeholder."""
    return bool(_VAR_PATTERN.search(text))


def resolve_curly_placeholders(
    text: str,
    resolver: Callable[[str], Optional[str]],
) -> str:
    """Replace all {varName} placeholders in a string.

    Same semantics as :func:`resolve_placeholders` but matches ``{name}``
    instead of ``#{name}``.
    """
    def replacer(match: re.Match) -> str:
        var_name = match.group(1)
        value = resolver(var_name)
        if value is not None:
            return value
        return match.group(0)

    return _CURLY_PATTERN.sub(replacer, text)


def has_curly_placeholders(text: str) -> bool:
    """Return True if the string contains at least one {varName} placeholder."""
    return bool(_CURLY_PATTERN.search(text))


def find_all_placeholders(text: str) -> list:
    """Return all variable names from #{varName} and {varName} placeholders."""
    names = []
    names.extend(m.group(1) for m in _VAR_PATTERN.finditer(text))
    names.extend(m.group(1) for m in _CURLY_PATTERN.finditer(text))
    return names


