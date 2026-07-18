"""CLI 参数 schema 加载与 argparse 辅助函数。
CLI argument schema loading and argparse helper functions.

从 shared/schemas/cli/*.json 读取参数定义，提供自动生成
argparse parser 的功能，确保 Python 端与 TypeScript 端参数一致。
Reads arg definitions from shared/schemas/cli/*.json and provides
auto-generation of argparse parsers, keeping Python and TypeScript in sync.
"""

from __future__ import annotations

import json
from pathlib import Path

# JSON schema 目录 — shared/schemas/cli/
# JSON schema directory — shared/schemas/cli/
_SCHEMA_DIR = Path(__file__).parent.parent.parent / "schemas" / "cli"


def load_cli_schema(entry: str) -> dict:
    """加载 CLI 参数 schema 文件。

    从 shared/schemas/cli/<entry>.json 加载参数定义。
    Load CLI arg schema from shared/schemas/cli/<entry>.json.

    Args:
        entry: 入口名称（'agent', 'executor', 'converter'）
               Entry name ('agent', 'executor', 'converter')

    Returns:
        dict: schema 数据 / schema data
    """
    path = _SCHEMA_DIR / f"{entry}.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _arg_kwargs(arg: dict) -> dict:
    """将 schema 参数定义映射到 argparse.add_argument 的 kwargs。

    处理类型映射：str → {}, int → {"type": int},
    bool_store_true → {"action": "store_true"} 等。
    Map schema arg definition to argparse.add_argument kwargs.
    """
    t = arg.get("type", "str")
    # 默认值：null 表示不传 default / null means don't pass default
    default = arg.get("default")

    if t == "int":
        kwargs = {"type": int}
    elif t == "float":
        kwargs = {"type": float}
    elif t == "bool_store_true":
        kwargs = {"action": "store_true"}
    elif t == "bool_store_false":
        kwargs = {"action": "store_false"}
    else:
        kwargs = {"type": str}

    if default is not None:
        kwargs["default"] = default
    elif t in ("bool_store_true", "bool_store_false"):
        # schema 中 default 为 null → 传递 None 供业务逻辑区分"未指定用户输入"
        # null default in schema → pass None so business logic can distinguish "user didn't specify"
        kwargs["default"] = None

    if arg.get("choices"):
        kwargs["choices"] = arg["choices"]

    if arg.get("nargs"):
        kwargs["nargs"] = arg["nargs"]

    if arg.get("required"):
        kwargs["required"] = True

    return kwargs


def add_args_to_parser(parser, schema: dict, exclude_dest: set | None = None):
    """将 schema 中定义的参数注册到 argparse.ArgumentParser。

    遍历 schema["args"]，对每个参数调用 parser.add_argument()。
    Register args defined in schema onto an argparse.ArgumentParser.

    Args:
        parser: argparse.ArgumentParser 实例 / instance
        schema: CLI schema dict (from load_cli_schema)
        exclude_dest: 要排除的 dest 名称集合（如 {"studio"}，因为 --studio
                       由 Rust 端注入，不暴露给普通 CLI 用户）
                      Set of dest names to exclude (e.g. {"studio"}, since
                      --studio is injected by Rust side, not for normal CLI)
    """
    exclude = exclude_dest or set()

    for a in schema.get("args", []):
        if a["dest"] in exclude:
            continue

        # 构建参数名列表：先 flag，再 short / Build name list: flag first, then short
        names = [a["flag"]]
        if a.get("short"):
            names.append(a["short"])

        kwargs = _arg_kwargs(a)
        # 帮助文本：中文 + 英文 / Help text: Chinese + English
        kwargs["dest"] = a["dest"]
        kwargs["help"] = f'{a.get("help_zh", "")} / {a.get("help_en", "")}'

        parser.add_argument(*names, **kwargs)


def add_subcommand_args(subparsers, schema: dict):
    """为 converter 注册子命令及其参数。

    遍历 schema["subcommands"]，为每个子命令创建 subparser 并注册参数。
    Register subcommands and their args for converter.

    Args:
        subparsers: argparse._SubParsersAction 实例 / instance
        schema: converter CLI schema dict
    """
    for name, sc in schema.get("subcommands", {}).items():
        p = subparsers.add_parser(
            name,
            help=f'{sc.get("description_zh", "")} / {sc.get("description_en", "")}',
        )
        add_args_to_parser(p, {"args": sc.get("args", [])})


def get_editable_dests(schema: dict, section: str | None = None) -> set[str]:
    """获取某 section 下所有 studio 可编辑的参数 dest。

    供 Python 端确认哪些参数应由 studio 前端控制。
    Get all studio-editable arg dests for a given section.
    Used by Python side to know which args the studio frontend controls.

    Args:
        schema: CLI schema dict
        section: 配置节名称，None 表示返回所有可编辑参数
                 Config section name, None returns all editable args

    Returns:
        set[str]: 可编辑参数的 dest 集合 / set of editable arg dests
    """
    result = set()
    for a in schema.get("args", []):
        if a.get("studio", {}).get("editable") and (section is None or a.get("section") == section):
            result.add(a["dest"])
    return result
