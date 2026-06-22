"""Field name mapping between snake_case (YAML / Agent dataclass) and PascalCase (Excel column headers)."""

# Columns whose values are JSON objects/arrays in memory but JSON strings in Excel
JSON_COLUMNS = frozenset({
    "request_head", "request_body", "assert_dict", "assert_rules",
    "preprocessors", "postprocessors",
})

# snake_case → PascalCase
SNAKE_TO_PASCAL: dict[str, str] = {
    "test_id": "TestID",
    "api_name": "APIName",
    "app_name": "AppName",
    "method": "Method",
    "url": "URL",
    "request_head": "RequestHead",
    "request_body": "RequestBody",
    "status_code": "StatusCode",
    "assert_dict": "AssertDict",
    "assert_rules": "AssertRules",
    "preprocessors": "PreProcessors",
    "postprocessors": "PostProcessors",
    "remark": "Remark",
    "relevance_id": "RelevanceID",
    "tag": "Tag",
    "step_id": "StepID",
    "inherit": "Inherit",
}

# PascalCase → snake_case
PASCAL_TO_SNAKE: dict[str, str] = {v: k for k, v in SNAKE_TO_PASCAL.items()}


def snake_to_pascal(snake_name: str) -> str:
    """Convert a single snake_case field name to PascalCase."""
    return SNAKE_TO_PASCAL.get(snake_name, snake_name)


def pascal_to_snake(pascal_name: str) -> str:
    """Convert a single PascalCase field name to snake_case."""
    return PASCAL_TO_SNAKE.get(pascal_name, pascal_name)


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


