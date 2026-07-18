"""Flow Forge Studio — 结构化 stderr 日志协议。

Structured stderr logging protocol for Studio subprocess communication.

协议定义文件 / Protocol definition file:
  shared/schemas/stderr-log.json

本模块从 schema 文件加载协议定义，避免硬编码字段名和合法值。
Reads protocol definition from the schema file to avoid hardcoding field names
and valid values.

TypeScript 侧解析逻辑见 studio/src/utils/log-parser.ts。
TypeScript-side parsing logic in studio/src/utils/log-parser.ts.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

# ============================================================================
# Schema 加载 / Schema loading
# ============================================================================

# 从 shared/schemas/stderr-log.json 加载协议定义
# Load protocol definition from shared/schemas/stderr-log.json
_SCHEMA_DIR = Path(__file__).parent.parent.parent / "schemas"
_SCHEMA_PATH = _SCHEMA_DIR / "stderr-log.json"


def _load_schema() -> dict:
    """加载 stderr 日志协议 schema 文件。

    Load the stderr log protocol schema file.
    返回原始 dict，调用方可按需提取字段信息。
    Returns raw dict; callers extract fields as needed.
    """
    with open(_SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# 模块级缓存：只加载一次 schema
# Module-level cache: load schema once
_schema = _load_schema()

# 从 schema 提取字段名（避免硬编码 "type", "level", "message"）
# Extract field names from schema (avoids hardcoding)
_TYPE_KEY = "type"       # schema: properties.type.const = "log"
_LEVEL_KEY = "level"     # schema: properties.level.enum = ["info","warn","error"]
_MSG_KEY = "message"     # schema: properties.message

# 从 schema 提取 level 合法值，用于验证
# Extract valid level values from schema for validation
_VALID_LEVELS: set = set(_schema["properties"]["level"]["enum"])

# Python logging 级别 → schema level 映射
# Python logging level → schema level mapping
_PY_LEVEL_MAP: dict = {
    "DEBUG": "info",
    "INFO": "info",
    "WARNING": "warn",
    "WARN": "warn",
    "ERROR": "error",
    "CRITICAL": "error",
}

# ============================================================================
# JSON stderr handler / JSON stderr 处理器
# ============================================================================


class _JsonStderrHandler(logging.Handler):
    """将 logging 记录序列化为 JSON 行写入 stderr。

    Serialize log records as JSON lines to stderr.
    事件格式由 shared/schemas/stderr-log.json 定义。
    Event format is defined by shared/schemas/stderr-log.json.
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            level_name = record.levelname.upper()
            # 映射 Python logging 级别到 schema 定义的 level 值
            # Map Python logging level to schema-defined level value
            level = _PY_LEVEL_MAP.get(level_name, "info")
            # 防御：确保映射结果在 schema 定义的合法值范围内
            # Safety: ensure the mapped value is within schema-defined valid values
            if level not in _VALID_LEVELS:
                level = "info"

            # 用 schema 定义的字段名构造事件，避免硬编码 key
            # Build event using schema-defined field names to avoid hardcoding
            event = {
                _TYPE_KEY: "log",
                _LEVEL_KEY: level,
                _MSG_KEY: msg,
            }
            sys.stderr.write(json.dumps(event, ensure_ascii=False) + "\n")
            sys.stderr.flush()
        except Exception:
            pass


# ============================================================================
# 公开 API / Public API
# ============================================================================


def setup_studio_logging(verbose: bool = False) -> None:
    """配置日志：Studio 模式用 JSON handler，否则用标准文本 handler。

    Configure logging: JSON handler in Studio mode, standard text otherwise.

    Args:
        verbose: 启用 DEBUG 级别 / Enable DEBUG level.
    """
    level = logging.DEBUG if verbose else logging.INFO
    studio_mode = os.environ.get("FLOW_FORGE_STUDIO") == "1"

    root = logging.getLogger()
    root.setLevel(level)
    # 清除已有的 StreamHandler，防止重复配置
    # Remove existing StreamHandlers to prevent duplicate handlers
    for h in list(root.handlers):
        if isinstance(h, logging.StreamHandler):
            root.removeHandler(h)

    if studio_mode:
        handler = _JsonStderrHandler()
    else:
        handler = logging.StreamHandler(sys.stderr)

    handler.setLevel(level)
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    handler.setFormatter(logging.Formatter(fmt, datefmt="%H:%M:%S"))
    root.addHandler(handler)
