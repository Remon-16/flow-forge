#!/usr/bin/env python3
"""H2 JDBC jar 初始化脚本（跨平台 CLI，中英双语提示）。
H2 JDBC jar bootstrap CLI (cross-platform, bilingual zh/en messages).

用法 / Usage::

    python tools/h2/init_h2.py                  # 下载到默认目录 ~/.flow-forge/h2/
    python tools/h2/init_h2.py --dir D:/h2      # 下载到自定义目录
    python tools/h2/init_h2.py --check          # 仅检查是否已就绪
    python tools/h2/init_h2.py --force          # 强制重新下载
    python tools/h2/init_h2.py --lang en        # 强制英文输出

说明：本脚本只为 flow-forge 准备 H2 JDBC jar（供 python/processors 的 H2
SQLAlchemy 方言通过 JayDeBeApi 加载），不启动任何 H2 服务。foli-mall 后端启动时
会自动开启 H2 TCP Server（默认端口 9092）。

Note: this script only prepares the H2 JDBC jar for flow-forge (loaded by the
H2 SQLAlchemy dialect via JayDeBeApi); it does not start any H2 service. The
foli-mall backend starts an H2 TCP Server (default port 9092) on boot.
"""

import argparse
import locale
import os
import sys
from pathlib import Path
from typing import List, Optional

# 将仓库 python/ 目录加入 sys.path，以便复用 i18n 与 processors.h2_support。
# Add the repo python/ directory to sys.path to reuse i18n and processors.h2_support.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_PYTHON_DIR = _REPO_ROOT / "python"
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

from i18n import _, set_lang  # noqa: E402
from processors.h2_support import (  # noqa: E402
    ALIYUN_MIRROR_URL,
    DEFAULT_H2_DIR,
    H2_JAR_FILENAME,
    H2_VERSION,
    MAVEN_CENTRAL_URL,
    download_h2_jar,
    resolve_jar_path,
    verify_sha256,
)


def _pre_scan_lang(argv: List[str]) -> Optional[str]:
    """在 argparse 解析前预扫描 --lang，用于设置帮助信息语言。
    Pre-scan --lang before argparse parsing so help text uses the right language."""
    if "--lang" in argv:
        idx = argv.index("--lang")
        if idx + 1 < len(argv) and argv[idx + 1] in ("zh", "en"):
            return "zh_CN" if argv[idx + 1] == "zh" else "en_US"
    for arg in argv:
        if arg.startswith("--lang="):
            val = arg.split("=", 1)[1]
            if val == "zh":
                return "zh_CN"
            if val == "en":
                return "en_US"
    return None


def _detect_lang() -> str:
    """自动检测语言（zh_CN 或 en_US）。
    Auto-detect the language (zh_CN or en_US)."""
    env_lang = os.environ.get("AGENT_LANG", "").strip()
    if env_lang:
        return env_lang if env_lang.lower().startswith("en") else "zh_CN"
    try:
        loc, _ = locale.getlocale()
        if loc:
            if loc.lower().startswith("zh"):
                return "zh_CN"
            if loc.lower().startswith("en"):
                return "en_US"
    except Exception:
        pass
    return "en_US" if os.environ.get("LANG", "").lower().startswith("en") else "zh_CN"


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。Build the command line argument parser."""
    parser = argparse.ArgumentParser(
        prog="init_h2",
        description=_("h2.cli.description"),
    )
    parser.add_argument(
        "--version",
        default=H2_VERSION,
        help=_("h2.cli.version_help"),
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=DEFAULT_H2_DIR,
        help=_("h2.cli.dir_help"),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=_("h2.cli.check_help"),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help=_("h2.cli.force_help"),
    )
    parser.add_argument(
        "--lang",
        choices=("zh", "en", "auto"),
        default="auto",
        help=_("h2.cli.lang_help"),
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """CLI 入口。CLI entry point."""
    argv = list(sys.argv[1:] if argv is None else argv)

    pre_lang = _pre_scan_lang(argv)
    set_lang(pre_lang if pre_lang else _detect_lang())

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.lang == "zh":
        set_lang("zh_CN")
    elif args.lang == "en":
        set_lang("en_US")

    if args.version != H2_VERSION:
        print(
            _("h2.cli.unsupported_version", version=args.version, supported=H2_VERSION),
            file=sys.stderr,
        )
        return 2

    if args.check:
        found = resolve_jar_path()
        if found is not None and verify_sha256(found):
            print(_("h2.cli.check_ok", path=str(found)))
            return 0
        print(_("h2.cli.check_missing"))
        return 1

    try:
        target = download_h2_jar(dest_dir=args.dir, force=args.force)
    except Exception as exc:  # noqa: BLE001 - CLI 需要兜底输出错误
        print(_("h2.cli.download_failed", error=str(exc)), file=sys.stderr)
        print(
            _(
                "h2.cli.download_failed_hint",
                url=MAVEN_CENTRAL_URL,
                mirror=ALIYUN_MIRROR_URL,
            ),
            file=sys.stderr,
        )
        return 1

    print(_("h2.cli.ready", path=str(target)))

    if Path(args.dir).expanduser() != DEFAULT_H2_DIR:
        print(
            _(
                "h2.cli.custom_dir_hint",
                env="H2_JAR_DIR",
                dir=str(Path(args.dir).expanduser()),
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
