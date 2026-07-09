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


# 需要将裸字符串包装为对象列表的 JSON 字段
# JSON fields whose bare-string values should be wrapped as list-of-dicts
_LIST_OF_DICT_FIELDS = {"preprocessors", "postprocessors"}


def _normalize_json_field(field_name: str, value: str) -> object:
    """将 JSON 解析失败的字符串值规范化为标准格式。
       Normalize a string value that failed JSON parsing into standard format.

       对 preprocessors/postprocessors 字段：
       - "print-demo" → [{"name": "print-demo", "config": {}}]
       - "hmac-sign,print-demo" → [{"name": "hmac-sign", ...}, {"name": "print-demo", ...}]
    """
    if field_name not in _LIST_OF_DICT_FIELDS:
        return value
    # 逗号分隔的多个处理器 / comma-separated processor names
    names = [n.strip() for n in value.split(",") if n.strip()]
    return [{"name": n, "config": {}} for n in names]


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
                # 尝试规范化简单格式 / try to normalize simple formats
                result[snake_key] = _normalize_json_field(snake_key, value)
        else:
            result[snake_key] = value
    return result


