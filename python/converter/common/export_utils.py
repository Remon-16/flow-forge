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
from .utils import sanitize_name

logger = logging.getLogger(__name__)

# ============================================================================
# 模板常量（Template constants）
# ============================================================================

FF_COMPAT_TEMPLATE = r'''"""Flow Forge 兼容层 — 让打包后的处理器可在无 Flow Forge 框架环境下运行。
   Flow Forge compatibility layer — lets bundled processors run without the
   Flow Forge framework.

提供处理器基类再导出、最小 i18n 与 app 配置访问。
Provides processor base-class re-exports, a minimal i18n fallback and app
config access.
"""

from typing import Any, Dict, Optional

# 处理器基类/异常从打包的 _processors.base 再导出，供自定义处理器使用。
# Re-export processor base classes/errors from the bundled _processors.base so
# custom processors keep working.
from _processors.base import (  # noqa: F401
    BaseExternalPlugin,
    PostProcessor,
    PreProcessor,
    ProcessorError,
    _PRE_PROCESSOR_REGISTRY,
    _POST_PROCESSOR_REGISTRY,
    _create_external_plugin_wrappers,
    _mask_password,
)


def _(message: str, **kwargs: Any) -> str:
    """最小 i18n 兼容：返回原文并格式化占位符。
       Minimal i18n fallback: return the message with placeholders formatted."""
    if kwargs:
        try:
            return message.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return message
    return message


def get_app(app_name: str) -> Optional[Dict[str, Any]]:
    """从生成目录的 _config.APPS 读取应用配置，并注入 _app_name。
       Read app config from the generated _config.APPS and inject _app_name."""
    try:
        from _config import APPS
    except ImportError:
        return None
    app = APPS.get(app_name)
    if isinstance(app, dict):
        app = dict(app)
        app.setdefault("_app_name", app_name)
    return app
'''


# ============================================================================
# python/ 根目录（内置处理器与框架依赖模块的源目录）
# python/ root (source of built-in processors and framework dependency modules)
# ============================================================================

_PYTHON_ROOT = Path(__file__).resolve().parent.parent.parent

# 整包打包时复制的框架包：源相对路径 → 生成目录目标包名。
# Framework packages copied during whole-package bundling: source rel path →
# destination package name in the generated directory.
_BUNDLE_PACKAGES: tuple[tuple[str, str], ...] = (
    ("processors", "_processors"),
    ("auth", "_auth"),
    ("resolvers", "_resolvers"),
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
        # 环境名可能含连字符等非法标识符字符（如 env-plugin-test.yml），
        # 生成模块名时统一替换为下划线。
        # Env names may contain characters invalid in identifiers (e.g.
        # env-plugin-test.yml); sanitize the generated module name.
        mod_name = sanitize_name(name)
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
        out_path = Path(output_dir) / f"_env_{mod_name}.py"
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
        mod_name = sanitize_name(env)
        config_lines.append(f"if ENV == \"{env}\":")
        config_lines.append(f"    from _env_{mod_name} import APPS  # noqa: E402, F401")

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


# 统一 import 重写规则：Flow Forge 框架 import → 生成目录内的打包包。
# Unified import rewrite rules: Flow Forge framework imports → bundled
# packages inside the generated directory.
_IMPORT_REWRITES: tuple[tuple[str, str], ...] = (
    ("from processors.", "from _processors."),
    ("import processors.", "import _processors."),
    ("from auth.", "from _auth."),
    ("from resolvers.", "from _resolvers."),
    ("from i18n import", "from _ff_compat import"),
    ("from config.config_manager import", "from _ff_compat import"),
    # db.py 中以字符串注册 H2 方言，需一并改写。
    # The H2 dialect is registered by name string in db.py; rewrite it too.
    ('"processors.h2_dialect"', '"_processors.h2_dialect"'),
)


def _rewrite_imports(content: str) -> str:
    """重写 Flow Forge 框架 import 为生成目录内的相对包。
       Rewrite Flow Forge framework imports to the bundled packages."""
    for old, new in _IMPORT_REWRITES:
        content = content.replace(old, new)
    return content


def _copy_package(src_dir: Path, dest_dir: Path) -> int:
    """递归复制 Python 包（排除 __pycache__）并对每个 .py 重写 import。
       Recursively copy a Python package (excluding __pycache__) and rewrite
       imports in every copied .py file."""
    count = 0
    for py_file in sorted(src_dir.rglob("*.py")):
        if "__pycache__" in py_file.parts:
            continue
        rel = py_file.relative_to(src_dir)
        dest_file = dest_dir / rel
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        dest_file.write_text(
            _rewrite_imports(py_file.read_text(encoding="utf-8")),
            encoding="utf-8",
        )
        logger.info(
            _("converter.bundled_processor", name=str(rel).replace("\\", "/"))
        )
        count += 1
    return count


def bundle_processors(
    output_dir: str,
    custom_processors_dir: str | None = None,
) -> int:
    """整包打包处理器及其配套依赖到生成目录。

       Bundle the whole processors package and its framework dependencies
       into the generated directory.

       复制 python/processors（含 builtin 全量）、python/auth、python/resolvers
       到 _processors/、_auth/、_resolvers/，并统一重写 Flow Forge import；
       自定义处理器（custom_processors_dir）复制到 _processors/ 根目录。
       后续新增内置处理器或用户自定义处理器无需再改本函数。

       Copies python/processors (including all builtin processors),
       python/auth and python/resolvers into _processors/, _auth/ and
       _resolvers/ with unified import rewriting; custom processors from
       custom_processors_dir are copied into the _processors/ root.
       Future built-in or user-defined processors need no changes here.
    """
    output_root = Path(output_dir)
    base_dir = output_root / "_processors"
    # 确保 _processors 是 Python 包 / Ensure _processors is a Python package
    count = 0
    base_dir.mkdir(parents=True, exist_ok=True)
    _ensure_package(base_dir)

    # 整包复制处理器包及其框架依赖 / Whole-package copy of processors + deps
    for rel_src, rel_dest in _BUNDLE_PACKAGES:
        src = _PYTHON_ROOT / rel_src
        if not src.is_dir():
            continue
        dest = output_root / rel_dest
        n = _copy_package(src, dest)
        count += n
        logger.info(
            _("converter.bundling_package", src=str(src), dest=str(dest), count=n)
        )

    # 复制自定义处理器到 _processors/ 根目录 / Copy custom processors to root
    if custom_processors_dir:
        custom_src = Path(custom_processors_dir)
        if custom_src.is_dir():
            for py_file in sorted(custom_src.glob("*.py")):
                stem = py_file.stem
                if stem.startswith("_") or stem in {"base", "loader", "runner", "__init__"}:
                    continue
                dest_file = base_dir / py_file.name
                if dest_file.exists():
                    logger.warning(
                        _("converter.processor_overwrite",
                          name=py_file.name, source=str(py_file))
                    )
                dest_file.write_text(
                    _rewrite_imports(py_file.read_text(encoding="utf-8")),
                    encoding="utf-8",
                )
                logger.info(_("converter.bundled_processor", name=py_file.name))
                count += 1

    return count
