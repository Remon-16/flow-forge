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
# 内置处理器源目录（相对于 python/ 根目录）
# Built-in processor source directories (relative to python/ root)
# ============================================================================

_BUILTIN_PRE_DIR = str(
    Path(__file__).resolve().parent.parent.parent
    / "processors" / "builtin" / "pre"
)
_BUILTIN_POST_DIR = str(
    Path(__file__).resolve().parent.parent.parent
    / "processors" / "builtin" / "post"
)


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


def _ensure_package(dir_path: Path) -> None:
    """确保目录是一个 Python 包（创建 __init__.py）。
       Ensure the directory is a Python package by creating __init__.py."""
    dir_path.mkdir(parents=True, exist_ok=True)
    init_file = dir_path / "__init__.py"
    if not init_file.exists():
        init_file.write_text("", encoding="utf-8")


def _copy_and_rewrite_processor(src_file: Path, dest_dir: Path) -> bool:
    """复制单个处理器文件并重写 Flow Forge import。
       Copy a single processor file and rewrite Flow Forge imports to _ff_compat.

       如果目标文件已存在（自定义处理器覆盖内置），记录警告。
       If destination exists (custom overrides built-in), log warning.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / src_file.name
    if dest_file.exists():
        logger.warning(
            _("converter.processor_overwrite",
              name=src_file.name, source=str(src_file))
        )

    content = src_file.read_text(encoding="utf-8")
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

    dest_file.write_text(content, encoding="utf-8")
    logger.info(_("converter.bundled_processor", name=src_file.name))
    return True


def bundle_processors(
    output_dir: str,
    custom_processors_dir: str | None = None,
    builtin_pre_dir: str | None = None,
    builtin_post_dir: str | None = None,
) -> int:
    """复制所有处理器（内置 + 自定义）到 _processors/，统一替换 import。
       Bundle all processors (built-in + custom) into _processors/ with rewritten imports.

       内置处理器从 processors/builtin/pre/ 和 processors/builtin/post/ 复制。
       自定义处理器从 custom_processors_dir 复制。
       所有文件的 from processors.base import → from _ff_compat import。
    """
    if builtin_pre_dir is None:
        builtin_pre_dir = _BUILTIN_PRE_DIR
    if builtin_post_dir is None:
        builtin_post_dir = _BUILTIN_POST_DIR

    base_dir = Path(output_dir) / "_processors"
    count = 0

    # 确保 _processors 是 Python 包 / Ensure _processors is a Python package
    base_dir.mkdir(parents=True, exist_ok=True)
    _ensure_package(base_dir)

    # 复制内置前置处理器到 _processors/pre/ / Copy built-in preprocessors
    pre_dest = base_dir / "pre"
    _ensure_package(pre_dest)
    pre_path = Path(builtin_pre_dir)
    if pre_path.is_dir():
        for py_file in sorted(pre_path.glob("*.py")):
            if py_file.stem == "__init__":
                continue
            if _copy_and_rewrite_processor(py_file, pre_dest):
                count += 1

    # 复制内置后置处理器到 _processors/post/ / Copy built-in postprocessors
    post_dest = base_dir / "post"
    _ensure_package(post_dest)
    post_path = Path(builtin_post_dir)
    if post_path.is_dir():
        for py_file in sorted(post_path.glob("*.py")):
            if py_file.stem == "__init__":
                continue
            if _copy_and_rewrite_processor(py_file, post_dest):
                count += 1

    # 复制自定义处理器到 _processors/ 根目录 / Copy custom processors to root
    if custom_processors_dir:
        custom_src = Path(custom_processors_dir)
        if custom_src.is_dir():
            for py_file in sorted(custom_src.glob("*.py")):
                stem = py_file.stem
                if stem.startswith("_") or stem in {"base", "loader", "runner", "__init__"}:
                    continue
                if _copy_and_rewrite_processor(py_file, base_dir):
                    count += 1

    return count
