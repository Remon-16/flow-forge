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
        "--api", nargs="+",
        help="API 文档路径（支持多个文件）(OpenAPI .yaml/.json 或 Markdown .md)。API documentation path(s).",
    )
    p.add_argument(
        "--output",
        default=f"output_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        help="输出根目录。Output root directory (default: ./output_<timestamp>).",
    )
    p.add_argument(
        "--output-format", choices=["yaml", "excel", "both"], default=None,
        help="输出格式: yaml, excel, both (default: both, or from env.yaml).",
    )
    p.add_argument(
        "--debug-snapshots", action="store_true",
        help="保存调试快照 (interfaces.json + extracted_texts.json)。",
    )
    p.add_argument(
        "--plugin-batch-size", type=int, default=None,
        help="插件处理批次大小 (-1=不分批, 默认取自 env.yaml)。Plugin batch size (default from env.yaml).",
    )
    p.add_argument(
        "--max-steps", type=int, default=None,
        help="最大智能体步数 (默认取自 env.yaml)。Max agent steps.",
    )
    p.add_argument(
        "--max-retries", type=int, default=None,
        help="LLM 调用最大重试次数 (默认取自 env.yaml)。Max LLM call retries.",
    )
    p.add_argument(
        "--skeleton-batch-size", type=int, default=None,
        help="骨架生成分批大小 (默认取自 env.yaml)。Skeleton batch size.",
    )
    p.add_argument(
        "--plan-single-batch-size", type=int, default=None,
        help="单接口测试点分组大小 (默认取自 env.yaml)。Single API batch size.",
    )
    p.add_argument(
        "--url-doc-match-max-retries", type=int, default=None,
        help="URL 文档匹配纠错重试次数 (默认取自 env.yaml)。URL doc-match correction retries.",
    )
    p.add_argument(
        "--case-format-max-retries", type=int, default=None,
        help="用例格式校验重试次数 (默认取自 env.yaml)。Case format validation retries.",
    )
    p.add_argument(
        "--url-doc-match-strategy", choices=["fail", "warn", "skip"], default=None,
        help="URL 文档匹配纠错策略 (默认取自 env.yaml): fail | warn | skip。URL doc-match correction strategy.",
    )
    p.add_argument(
        "--consecutive-batch-failure-limit", type=int, default=None,
        help="连续批次失败上限 (默认取自 env.yaml)。Consecutive batch failure limit.",
    )
    p.add_argument(
        "--max-steps-no-progress", type=int, default=None,
        help="进度无变化最大步数 (默认取自 env.yaml)。Max steps with no progress.",
    )
    p.add_argument(
        "--validation", action="store_true", default=None,
        help="启用用例格式校验。Enable case validation.",
    )
    p.add_argument(
        "--no-validation", action="store_true", default=None,
        help="禁用用例格式校验。Disable case validation.",
    )
    p.add_argument(
        "--url-doc-match-enabled", action="store_true", default=None,
        help="启用 URL 文档匹配校验。Enable URL doc-match validation.",
    )
    p.add_argument(
        "--no-url-doc-match-enabled", action="store_true", default=None,
        help="禁用 URL 文档匹配校验。Disable URL doc-match validation.",
    )
    p.add_argument(
        "--plugins", action="store_true", default=None,
        help="启用插件系统。Enable plugin system.",
    )
    p.add_argument(
        "--no-plugins", action="store_true", default=None,
        help="禁用插件系统。Disable plugin system.",
    )
    p.add_argument(
        "--skills", action="store_true", default=None,
        help="启用 Skill 注入。Enable skill injection.",
    )
    p.add_argument(
        "--no-skills", action="store_true", default=None,
        help="禁用 Skill 注入。Disable skill injection.",
    )
    p.add_argument(
        "--lang", default=None,
        help="界面语言 (zh_CN / en_US, 默认取自 env.yaml)。UI language.",
    )
    p.add_argument(
        "--prompt", "-p", default=None,
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
        "--parser-path", default=None,
        help="自定义解析器 .py 路径 (仅 --parse-mode rule)。Custom parser path.",
    )
    p.add_argument(
        "--reference-dir", default=None,
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
        "--case-type", choices=["single", "biz", "both"], default=None,
        help="用例生成类型: single=仅单接口, biz=仅业务链路, both=全部 (默认)。Case type.",
    )
    p.add_argument(
        "--log-to-output", action="store_true", default=None,
        help="将日志持久化到输出目录 ({output_dir}/logs/agent.log)。Persist logs to output dir.",
    )
    p.add_argument(
        "--studio", action="store_true",
        help="Studio 子进程模式 (JSON 协议通信)。Studio subprocess mode (JSON protocol).",
    )
    return p
