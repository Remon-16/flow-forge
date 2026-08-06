#!/usr/bin/env python3
"""诊断计数器 / Diagnostic counter — 每 3 秒输出递增数字，用于测试子进程管理。

Prints incrementing number every 3s to stdout + writes to output_count.txt.
Runs for 10 minutes (200 iterations, 3s each).

Usage:
    python counter_main.py --output-dir /path/to/output
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

# 注入 shared 包路径 — 使 flow_forge_schemas 可导入（与 main.py 一致）
# Inject shared package path — makes flow_forge_schemas importable (same as main.py)
_SHARED = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "shared", "py"))
if os.path.isdir(_SHARED) and _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

from flow_forge_schemas.cli import load_cli_schema, add_args_to_parser


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """从 shared/schemas/cli/counter.json 自动生成 parser。
    Auto-generate parser from shared/schemas/cli/counter.json."""
    schema = load_cli_schema("counter")
    parser = argparse.ArgumentParser(description="Flow Forge Diagnostic Counter")
    add_args_to_parser(parser, schema)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """运行计数循环 / Run counting loop."""
    args = _parse_args(argv)

    # 确保输出目录存在 / Ensure output directory exists
    os.makedirs(args.output_dir, exist_ok=True)
    filepath = os.path.join(args.output_dir, "output_count.txt")

    # 10 分钟 = 200 次迭代（每次 3 秒）/ 10 minutes = 200 iterations (3s each)
    total = 200
    for i in range(1, total + 1):
        # 每次独立操作：打开 → 写入 → 关闭 / Independent each time: open → write → close
        with open(filepath, "w") as f:
            f.write(str(i))

        # 输出到 stdout（studio 通过事件接收）/ Print to stdout (received by studio via events)
        print(i, flush=True)

        if i < total:
            time.sleep(3)

    # 输出 JSON 完成行，供 studio 解析 / Print JSON completion line for studio parsing
    print(json.dumps({"output": filepath, "total_counts": total}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
