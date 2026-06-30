"""converter 包公共工具函数。
   shared utility functions for the converter package."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Callable

import yaml

logger = logging.getLogger(__name__)

# ============================================================================
# YAML 读取（YAML reading）
# ============================================================================


def read_yaml_dir(
    dir_path: str | None,
    *,
    validator: Callable[[dict[str, object]], bool] | None = None,
) -> list[dict[str, object]]:
    """读取目录下所有 .yaml 文件，返回解析后的 dict 列表。
       Read all .yaml files from a directory, return parsed dicts.

       如果提供了 validator，仅保留通过验证的条目。
       If validator is provided, only entries passing it are kept.
    """
    if not dir_path:
        return []
    p = Path(dir_path)
    if not p.is_dir():
        logger.warning("Directory not found, skipping: %s", dir_path)
        return []
    results: list[dict[str, object]] = []
    for f in sorted(p.glob("*.yaml")):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
            if isinstance(data, dict):
                data.pop("case_type", None)
                if validator is None or validator(data):
                    results.append(data)
        except Exception:
            logger.warning("Failed to read YAML file: %s", f, exc_info=True)
    return results


# ============================================================================
# 命名工具（Naming utilities）
# ============================================================================

_NON_WORD_RE = re.compile(r"[^a-zA-Z0-9_]")


def sanitize_name(name: str) -> str:
    """将字符串转为合法 Python 标识符 — 替换非字母数字为下划线。
       Convert a string to a valid Python identifier — replace non-alphanumeric with underscore."""
    return _NON_WORD_RE.sub("_", str(name))


def indent_lines(text: str, spaces: int) -> str:
    """给非空行添加额外缩进。
       Add extra indentation to every non-empty line."""
    if not text:
        return text
    prefix = " " * spaces
    result = []
    for line in text.splitlines(True):
        if line.strip():
            result.append(prefix + line)
        else:
            result.append(line)
    return "".join(result)


_ILLEGAL_SHEET_CHARS_RE = re.compile(r"[:\\/*?\[\]]")


def safe_sheet_name(name: str) -> str:
    """清理 Excel 工作表名称 — 替换非法字符、截断到 31 字符。
       Sanitize Excel sheet name — replace illegal chars, truncate to 31 chars."""
    cleaned = _ILLEGAL_SHEET_CHARS_RE.sub("-", str(name))
    return cleaned[:31]


_FILENAME_ILLEGAL_RE = re.compile(r"[/\\:*?\"<>|]")


def safe_filename(name: str) -> str:
    """清理文件名 — 替换 \/:*?"<>| 为下划线。
       Sanitize filename — replace \/:*?"<>| with underscores."""
    return _FILENAME_ILLEGAL_RE.sub("_", str(name))
