import re
from typing import Callable, Optional

_VAR_PATTERN = re.compile(r"#\{([^}]+)\}")


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


def extract_placeholder_names(text: str) -> list:
    """Return a deduplicated list of variable names referenced via #{...}."""
    return list(dict.fromkeys(_VAR_PATTERN.findall(text)))
