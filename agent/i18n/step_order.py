"""流水线步骤编号定义。Pipeline step numbering.

调整流水线时只需修改 STEP_ORDER dict 和 TOTAL_STEPS。
When adjusting the pipeline, just update STEP_ORDER — step prefixes update automatically.
"""

STEP_ORDER: dict[str, int] = {
    "parse_docs": 1,
    "analyze_api": 2,
    "save_interfaces": 3,
    "analyze_requirement": 4,
    "generate_outline": 5,
    "generate_plan": 6,
    "review_plan": 7,
    "parse_plan": 8,
    "case_generation": 9,
    "write_output": 10,
}


def step_label(key: str) -> str:
    """返回步骤前缀，如 '[1/9]'。Return step prefix like '[1/9]'."""
    num = STEP_ORDER.get(key)
    if num is None:
        return ""
    total = len(STEP_ORDER)
    return f"[{num}/{total}]"


def step_msg(key: str, text: str, **kwargs) -> str:
    """组合步骤前缀 + 翻译文本。Combine step prefix + translated text."""
    prefix = step_label(key)
    formatted = text.format(**kwargs) if kwargs else text
    return f"{prefix} {formatted}" if prefix else formatted
