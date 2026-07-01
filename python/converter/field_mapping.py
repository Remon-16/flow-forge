"""字段名映射 — 从共享 schema 包重导出。
   Field name mapping — re-exported from the shared schema package."""

from flow_forge_schemas import (
    JSON_FIELDS as JSON_COLUMNS,
    SNAKE_TO_PASCAL,
    PASCAL_TO_SNAKE,
    snake_to_pascal,
    pascal_to_snake,
)

__all__ = [
    "JSON_COLUMNS", "SNAKE_TO_PASCAL", "PASCAL_TO_SNAKE",
    "snake_to_pascal", "pascal_to_snake", "convert_row_to_snake",
]


def convert_row_to_snake(
    row: dict[str, object], *, parse_json: bool = True
) -> dict[str, object]:
    """Convert an Excel row (PascalCase keys) to a snake_case dict.

    If *parse_json* is True, JSON column values are parsed from strings.
    """
    import json

    result: dict[str, object] = {}
    for pascal_key, value in row.items():
        snake_key = pascal_to_snake(pascal_key)
        if value is None or value == "":
            continue
        if parse_json and snake_key in JSON_COLUMNS and isinstance(value, str):
            try:
                result[snake_key] = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                result[snake_key] = value  # keep as-is on parse failure
        else:
            result[snake_key] = value
    return result


