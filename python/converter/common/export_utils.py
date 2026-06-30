"""公共导出基础设施 — 与目标格式无关，pytest/postman/jmeter 均可复用。
   Shared export infrastructure — format-agnostic, reusable across export targets."""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

import yaml

from i18n import _

logger = logging.getLogger(__name__)

# ============================================================================
# 模板常量（Template constants）
# ============================================================================

FF_COMPAT_TEMPLATE = r'''"""Minimal compatibility stubs for Flow Forge processors.

Provides PreProcessor / PostProcessor base classes and ProcessorError so that
custom processor modules can run without the Flow Forge framework.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Tuple


class ProcessorError(Exception):
    """Controlled error from a processor."""

    def __init__(self, message: str, processor_name: str = ""):
        super().__init__(message)
        self.processor_name = processor_name


class PreProcessor(ABC):
    """Minimal pre-processor base class."""

    name: str = ""

    @abstractmethod
    def process(
        self,
        headers: Dict[str, Any],
        body: Dict[str, Any],
        case_config: Dict[str, Any],
        global_config: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        ...


class PostProcessor(ABC):
    """Minimal post-processor base class."""

    name: str = ""

    @abstractmethod
    def process(
        self,
        request_headers: Dict[str, Any],
        request_body: Dict[str, Any],
        response_headers: Dict[str, Any],
        response_body: Any,
        case_config: Dict[str, Any],
        global_config: Dict[str, Any],
    ) -> None:
        ...
'''


# ============================================================================
# 处理器调度表（Processor dispatch maps）
# ============================================================================

# 内置前置处理器名 → conftest 函数名
# Built-in preprocessor name → conftest function name
PREPROC_DISPATCH: dict[str, str] = {
    "timestamp": "_apply_timestamp",
    "hmac-sign": "_apply_hmac_sign",
    "print-demo": "_print_request",
}

# 内置后置处理器名 → conftest 函数名
# Built-in postprocessor name → conftest function name
POSTPROC_DISPATCH: dict[str, str] = {
    "hmac-verify": "_verify_hmac",
    "response-time": "_log_response_metrics",
    "print-demo-post": "_print_response",
}


# ============================================================================
# 文件写入（File writers）
# ============================================================================

def write_ff_compat(output_dir: str) -> None:
    """写入 _ff_compat.py — 自定义处理器兼容适配层。
       Write _ff_compat.py — lightweight compatibility stubs for custom processors."""
    path = Path(output_dir) / "_ff_compat.py"
    path.write_text(FF_COMPAT_TEMPLATE, encoding="utf-8")
    logger.info(_("converter.wrote_ff_compat", path=str(path)))


def write_env_configs(output_dir: str, config_dir: str) -> None:
    """读取 env-*.yml 文件，生成 _config.py + _env_*.py。
       Read env-*.yml files, write _config.py + _env_*.py."""
    config_path = Path(config_dir)
    env_files = sorted(config_path.glob("env-*.yml"))
    if not env_files:
        logger.debug(_("converter.no_env_files", dir=config_dir))
        # 生成最小 _config.py（Generate minimal _config.py with empty APPS）
        minimal = '''"""Environment selector."""
ENV = "local"
APPS = {}
'''
        (Path(output_dir) / "_config.py").write_text(minimal, encoding="utf-8")
        return

    env_names: list[str] = []
    for f in env_files:
        name = f.stem.replace("env-", "")  # env-local.yml → local
        env_names.append(name)
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
        except Exception:
            logger.warning(_("converter.env_read_error", path=str(f)), exc_info=True)
            data = {}

        # 写入 _env_{name}.py（Write _env_{name}.py）
        env_py = f'''"""Auto-generated app configurations for '{name}' environment."""
APPS = {json.dumps(data, indent=4, ensure_ascii=False)}
'''
        out_path = Path(output_dir) / f"_env_{name}.py"
        out_path.write_text(env_py, encoding="utf-8")
        logger.info(_("converter.wrote_env_config", name=name, path=str(out_path)))

    # 写入 _config.py（Write _config.py — environment selector）
    first_env = env_names[0] if env_names else "local"
    config_lines = [
        '"""Environment selector — change ENV to switch between environments.',
        '',
        f'Available environments: {env_names}',
        '"""',
        f'ENV = "{first_env}"  # {" | ".join(env_names)}',
        '',
    ]
    for env in env_names:
        config_lines.append(f"if ENV == \"{env}\":")
        config_lines.append(f"    from _env_{env} import APPS  # noqa: E402, F401")

    config_py = "\n".join(config_lines) + "\n"
    (Path(output_dir) / "_config.py").write_text(config_py, encoding="utf-8")
    logger.info(_("converter.wrote_config_py", path=str(Path(output_dir) / "_config.py")))


def bundle_custom_processors(processors_dir: str | None, output_dir: str) -> int:
    """复制自定义处理器 .py 文件到 _custom_processors/，替换 Flow Forge import。
       Copy custom processor .py files, rewrite Flow Forge imports to _ff_compat.

       跳过内部模块（base, loader, runner）和内置处理器。
       Skips internal modules (base, loader, runner) and built-in processors.
    """
    if not processors_dir:
        return 0
    src = Path(processors_dir)
    if not src.is_dir():
        return 0

    dest = Path(output_dir) / "_custom_processors"
    internal = {"base", "loader", "runner", "__init__"}
    builtin_names = {"hmac_sign", "hmac_verify", "path_param_restore",
                     "print_demo", "response_time", "timestamp_sign"}
    count = 0
    for py_file in sorted(src.glob("*.py")):
        stem = py_file.stem
        if stem.startswith("_") or stem in internal or stem in builtin_names:
            continue
        content = py_file.read_text(encoding="utf-8")
        # 替换 Flow Forge import → 兼容层 import
        # Replace Flow Forge import → compat layer import
        content = content.replace(
            "from processors.base import", "from _ff_compat import"
        )
        content = content.replace(
            "from processors.base import PreProcessor, ProcessorError",
            "from _ff_compat import PreProcessor, ProcessorError",
        )
        content = content.replace(
            "from processors.base import PostProcessor, ProcessorError",
            "from _ff_compat import PostProcessor, ProcessorError",
        )

        dest.mkdir(parents=True, exist_ok=True)
        (dest / py_file.name).write_text(content, encoding="utf-8")
        logger.info(_("converter.bundled_processor", name=py_file.name))
        count += 1

    return count
