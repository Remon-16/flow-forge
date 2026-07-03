"""Simple string-template prompt renderer with {{variable}} substitution."""

import re
from typing import Any, Dict

_VAR_RE = re.compile(r"\{\{(\w+)\}\}")


def render_prompt(template: str, **kwargs: Any) -> str:
    """Replace {{variable}} placeholders with keyword argument values.

    Example:
        render_prompt("Hello {{name}}", name="World") -> "Hello World"
    """
    result = template
    for key, value in kwargs.items():
        # 先替换 {{key}}（纯字符串模板），再替换 {key}（f-string 模板）
        # Replace {{key}} (plain string templates) first, then {key} (f-string templates)
        result = result.replace(f"{{{{{key}}}}}", str(value))
        result = result.replace(f"{{{key}}}", str(value))
    # Warn about unresolved placeholders
    remaining = _VAR_RE.findall(result)
    if remaining:
        import logging
        logging.getLogger(__name__).warning(
            "Unresolved placeholders in template: %s", remaining
        )
    return result
