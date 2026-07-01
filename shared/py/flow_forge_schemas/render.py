# Prompt 渲染工具 — 从 JSON schema 动态生成 LLM prompt 文本。
# Prompt rendering utilities — dynamically generate LLM prompt text from JSON schemas.
"""
供 agent/prompts/ 和 agent/plugins/official/prompts/ 使用。
修改 shared/schemas/*.json 时，引用这些函数的 prompt 自动同步。

Used by agent/prompts/ and agent/plugins/official/prompts/.
When shared/schemas/*.json changes, prompts using these functions update automatically.
"""

import json
from pathlib import Path
from typing import Optional

_SCHEMAS = Path(__file__).parent.parent.parent / "schemas"


def _load(name: str):
    """加载 JSON 数据文件。 / Load a JSON data file."""
    with open(_SCHEMAS / f"{name}.json", encoding="utf-8") as f:
        return json.load(f)


def _resolve_fields(entity_type: str) -> list[dict]:
    """解析实体类型的完整字段列表（含继承展开）。
       Resolve the full field list for an entity type (with inheritance resolved).
    """
    types = _load("types")
    if entity_type not in types:
        raise ValueError(
            f"Unknown entity type '{entity_type}'. "
            f"Available: {list(types.keys())}"
        )

    entity = types[entity_type]

    # 没有继承 → 直接返回 / No inheritance → return directly
    if "extends" not in entity:
        return entity["fields"]

    # 继承展开 / Resolve inheritance
    base_type = entity["extends"]
    base_fields = _resolve_fields(base_type)

    # 应用字段替换 / Apply field replacements
    replacements = {f["name"]: f for f in entity.get("replace_fields", [])}
    removes = {f["name"] for f in entity.get("replace_fields", []) if f.get("remove")}

    result = []
    for f in base_fields:
        if f["name"] in removes:
            continue
        if f["name"] in replacements:
            result.append(replacements[f["name"]])
        else:
            result.append(f)

    # 添加额外字段 / Add extra fields
    result.extend(entity.get("extra_fields", []))
    return result


# ============================================================================
# 公共渲染函数 / Public rendering functions
# ============================================================================


def render_field_list(entity_type: str, lang: str = "en") -> str:
    """生成字段列表描述文本（含类型和说明），供 LLM prompt 使用。
       Generate a field list description (with types and descriptions) for LLM prompts.

       输出格式 / Output format:
         - field_name (type, 必填/required): 中文说明 / English description
         - field_name (type, 默认/default=VALUE): 中文说明 / English description

       Args:
           entity_type: 实体类型名 / entity type name
                        (interface_def, single_test_case, biz_step, biz_flow, api_summary)
           lang: 描述语言 / description language — "zh" 使用中文描述, "en" 使用英文描述
    """
    fields = _resolve_fields(entity_type)
    lines = []

    for f in fields:
        name = f["name"]
        ftype = f["type"]
        desc = f.get("description", "")

        # 提取指定语言的描述 / Extract description for the requested language
        if lang == "en" and " / " in desc:
            desc = desc.split(" / ", 1)[1]

        # 构建字段标记 / Build field annotations
        annotations = []
        if f.get("required"):
            annotations.append("必填" if lang == "zh" else "required")
        default = f.get("default")
        if default is not None and not f.get("required"):
            annotations.append(
                f"默认={default}" if lang == "zh" else f"default={default}"
            )

        meta = f"({ftype}, {', '.join(annotations)})" if annotations else f"({ftype})"
        lines.append(f"  - {name} {meta}: {desc}")

    return "\n".join(lines)


def render_json_example(
    entity_type: str, pascal_case: bool = False, indent: int = 2
) -> str:
    """生成 JSON 示例，供 LLM prompt 使用。
       Generate a JSON example for LLM prompts.

       使用 types.json 中定义的 example 和 default 构造示例值。
       Uses example and default values from types.json to construct the example.

       Args:
           entity_type: 实体类型名 / entity type name
           pascal_case: True 使用 PascalCase 键（Excel 格式）, False 使用 snake_case（YAML 格式）
           indent: JSON 缩进空格数 / JSON indentation spaces
    """
    fields = _resolve_fields(entity_type)
    fm = _load("field-mapping")

    obj = {}
    for f in fields:
        key = fm["snake_to_pascal"].get(f["name"], f["name"]) if pascal_case else f["name"]
        value = f.get("example") or f.get("default")
        if value is not None:
            # 尝试解析为 JSON（用于 list/dict 默认值）
            # Try parsing as JSON (for list/dict defaults)
            if isinstance(value, str) and (value.startswith("{") or value.startswith("[")):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    pass
        else:
            # 无 example 且无 default — 根据类型填入占位符
            # No example and no default — use placeholder based on type
            ftype = f.get("type", "string")
            if ftype in ("dict",):
                value = {}
            elif ftype in ("list",):
                value = []
            elif ftype in ("int",):
                value = 0
            elif ftype in ("bool",):
                value = True
            else:
                value = ""

        obj[key] = value

    return json.dumps(obj, ensure_ascii=False, indent=indent)


def render_operators_guide(lang: str = "en") -> str:
    """生成断言运算符说明文本，供 assertion prompt 使用。
       Generate an assertion operators guide for assertion prompts.

       从 operators.json 动态生成运算符列表、格式说明、合法函数和类型。
       Dynamically generates operator list, format rules, valid functions and types.

       Args:
           lang: 描述语言 / description language — "zh" 或 "en"
    """
    ops = _load("operators")
    is_zh = lang == "zh"

    lines = []
    fmt_note = (
        "断言规则格式: <jsonpath表达式> <运算符> [期望值]"
        if is_zh
        else "Assert rule format: <jsonpath expression> <operator> [expected value]"
    )
    lines.append(fmt_note)
    lines.append("")

    operator_header = "支持的运算符 / Supported operators:" if is_zh else "Supported operators:"
    lines.append(operator_header)

    for op in ops["operators"]:
        name = op["name"]
        if name == "is_not_null":
            desc = "值不为 null / value is not null" if is_zh else "value is not null"
        elif name == "is_null":
            desc = "值为 null / value is null" if is_zh else "value is null"
        elif name == "typeof":
            desc = (
                "类型检查 / type check (int, float, str, bool, list, dict, int_or_float)"
                if is_zh
                else "type check (int, float, str, bool, list, dict, int_or_float)"
            )
        elif name == "not_contains":
            desc = "不包含 / does not contain" if is_zh else "does not contain"
        elif name == "contains":
            desc = "包含 / contains" if is_zh else "contains"
        elif name == "in":
            desc = "在列表中 / is in list" if is_zh else "is in list"
        elif name == "=~":
            desc = "正则匹配 / regex match" if is_zh else "regex match"
        else:
            desc = (
                f"{'比较运算符' if is_zh else 'comparison operator'}"
            )
        lines.append(f"  - {name}: {desc}")

    lines.append("")

    func_header = (
        "支持的路径函数 / Supported path functions:"
        if is_zh
        else "Supported path functions:"
    )
    lines.append(func_header)
    for func in ops["valid_functions"]:
        if func == ".length()":
            desc = (
                "获取数组长度 / get array length"
                if is_zh
                else "get array length"
            )
        elif func == "SUM":
            desc = (
                "数组求和 / sum of array values"
                if is_zh
                else "sum of array values"
            )
        elif func == "SUM_PRODUCT":
            desc = (
                "两数组乘积和 / sum of products of two arrays"
                if is_zh
                else "sum of products of two arrays"
            )
        else:
            desc = ""
        lines.append(f"  - {func}: {desc}")

    lines.append("")
    typeof_header = (
        "typeof 合法类型 / Valid types for typeof:"
        if is_zh
        else "Valid types for typeof:"
    )
    lines.append(typeof_header)
    lines.append(f"  {', '.join(ops['valid_types'])}")

    return "\n".join(lines)


def render_field_constraints(entity_type: str, lang: str = "en") -> str:
    """生成字段约束说明 — 哪些字段由 LLM 填写，哪些不需要碰。
       Generate field constraint notes — which fields LLM should fill, which to skip.

       Args:
           entity_type: 实体类型名 / entity type name
           lang: 描述语言 / description language — "zh" 或 "en"
    """
    fields = _resolve_fields(entity_type)
    is_zh = lang == "zh"

    skip_fields = []
    json_fields = []
    fill_fields = []

    for f in fields:
        name = f["name"]
        if f.get("is_json"):
            json_fields.append(name)
            # JSON 字段通常由后续处理器填充 / JSON fields are typically filled by later processors
            skip_fields.append(name)
        elif name in ("test_id", "step_id", "relevance_id", "sheet_name"):
            fill_fields.append(name)
        elif name in ("api_name", "method", "url", "remark"):
            fill_fields.append(name)

    lines = []
    if fill_fields:
        header = "你需要填写的字段 / Fields you must fill:" if is_zh else "Fields you must fill:"
        lines.append(header)
        for name in fill_fields:
            desc = ""
            for f in fields:
                if f["name"] == name:
                    d = f.get("description", "")
                    if is_zh and " / " in d:
                        desc = f" — {d.split(' / ', 1)[0]}"
                    elif not is_zh and " / " in d:
                        desc = f" — {d.split(' / ', 1)[1]}"
                    elif d:
                        desc = f" — {d}"
                    break
            lines.append(f"  - {name}{desc}")
        lines.append("")

    if skip_fields:
        header = (
            "以下字段由后续步骤自动填充，不需要你填写 / "
            "The following fields are auto-filled by later steps, do NOT fill:"
        ) if is_zh else "The following fields are auto-filled by later steps, do NOT fill:"
        lines.append(header)
        for name in skip_fields:
            lines.append(f"  - {name}")
        lines.append("")

    if json_fields:
        note = (
            "注意: 标记为 JSON 格式的字段必须输出合法的 JSON 字符串（双引号）。"
            if is_zh
            else "Note: Fields marked as JSON format must output valid JSON strings (double quotes)."
        )
        lines.append(note)

    return "\n".join(lines)
