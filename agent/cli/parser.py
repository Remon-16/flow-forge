"""CLI 参数解析 — 从 shared/schemas/cli/agent.json 构建 ArgumentParser。
CLI argument parser: built from shared/schemas/cli/agent.json.
"""

import argparse
from datetime import datetime

# 从 shared schema 加载参数定义并自动生成 parser
# Load arg definitions from shared schema and auto-generate parser
from flow_forge_schemas.cli import load_cli_schema, add_args_to_parser


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。所有参数定义来自 shared/schemas/cli/agent.json。
    Build the command-line argument parser. All arg definitions from shared schema.
    """
    schema = load_cli_schema("agent")
    p = argparse.ArgumentParser(
        description="Flow Forge — API Test Case Generation Agent"
    )

    # 从 schema 自动注册所有参数（排除 --studio（Rust 端注入）和 --output（动态默认值））
    # Auto-register all args from schema (exclude --studio (Rust-injected) and --output (dynamic default))
    add_args_to_parser(p, schema, exclude_dest={"studio", "output"})

    # --output 需要动态默认值，手动添加 / --output needs dynamic default, add manually
    p.add_argument(
        "--output",
        default=f"output_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        help="输出根目录。Output root directory (default: ./output_<timestamp>).",
    )

    # --studio 由 Rust/Tauri 端注入，不暴露给普通 CLI 用户 / --studio injected by Rust side
    p.add_argument(
        "--studio", action="store_true",
        help="Studio 子进程模式（JSON 协议通信）。Studio subprocess mode (JSON protocol).",
    )

    return p
