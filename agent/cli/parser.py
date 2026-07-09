"""CLI 参数解析 — ArgumentParser 构建。

CLI argument parser: all command-line flags and options.
"""

import argparse
from datetime import datetime


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。

    Build the command-line argument parser.
    """
    p = argparse.ArgumentParser(
        description="Flow Forge — API Test Case Generation Agent"
    )
    p.add_argument(
        "--requirement", nargs="+",
        help="需求文档路径 (.txt, .md, .pdf)。Requirement document path(s).",
    )
    p.add_argument(
        "--api",
        help="API 文档路径 (OpenAPI .yaml/.json 或 Markdown .md)。API documentation path.",
    )
    p.add_argument(
        "--output",
        default=f"output_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        help="输出根目录。Output root directory (default: ./output_<timestamp>).",
    )
    p.add_argument(
        "--output-format", choices=["yaml", "excel", "both"], default="",
        help="输出格式: yaml, excel, both (default: both, or from env.yaml).",
    )
    p.add_argument(
        "--debug-snapshots", action="store_true",
        help="保存调试快照 (interfaces.json + extracted_texts.json)。",
    )
    p.add_argument(
        "--batch-size", type=int, default=0,
        help="每批最大用例数 (default: from env.yaml).",
    )
    p.add_argument(
        "--prompt", "-p", default="",
        help="用户补充指导，注入到计划和用例生成提示词中。User guidance.",
    )
    p.add_argument(
        "--env", default="env.yaml",
        help="配置文件路径。Path to config YAML file (default: env.yaml).",
    )
    p.add_argument(
        "-v", "--verbose", action="store_true",
        help="启用详细控制台日志。Enable verbose console logging.",
    )
    p.add_argument(
        "--debug", action="store_true",
        help="启用调试日志（完整 LLM I/O 写入 session debug.log）。",
    )
    p.add_argument(
        "--parse-mode", "-m", choices=["raw", "rule", "llm"], default="raw",
        help="API 文档解析模式 (default: raw): raw=LLM分析原文, rule=规则解析器, llm=LLM预提取.",
    )
    p.add_argument(
        "--parser-path", default="",
        help="自定义解析器 .py 路径 (仅 --parse-mode rule)。Custom parser path.",
    )
    p.add_argument(
        "--reference-dir", default="",
        help="增量更新参考目录。Reference directory for incremental updates.",
    )
    p.add_argument(
        "--resume", action="store_true",
        help="从已有 output 目录恢复执行。Resume from existing output directory.",
    )
    p.add_argument(
        "--resume-overwrite", action="store_true",
        help="恢复时覆盖已有输出。Overwrite existing output when resuming.",
    )
    p.add_argument(
        "--auto", action="store_true",
        help="自动模式：跳过所有人工审核，适合夜间批量生成。Auto mode: skip all human review.",
    )
    p.add_argument(
        "--case-type", choices=["single", "biz", "both"], default="",
        help="用例生成类型: single=仅单接口, biz=仅业务链路, both=全部 (默认)。Case type.",
    )
    p.add_argument(
        "--log-to-output", action="store_true", default=None,
        help="将日志持久化到输出目录 ({output_dir}/logs/agent.log)。Persist logs to output dir.",
    )
    return p
