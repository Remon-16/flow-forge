"""接口分析节点 — 分析 API 文档并生成结构化摘要。

analyze_api node: analyzes API docs and generates structured summaries.
"""

import importlib.util
import logging
from pathlib import Path
from typing import Dict, List

from doc_parser.markdown_parser import MarkdownParser
from doc_parser.openapi_parser import OpenApiParser
from graph.state import GraphState
from models.schema import InterfaceDef

from .helpers import _settings, _sl, save_snapshot, summary_to_interfaces

logger = logging.getLogger(__name__)


def analyze_api_node(state: GraphState) -> GraphState:
    """分析 API 文档，生成结构化摘要。

    Analyze API docs and generate structured summaries.
    Self-evaluates quality: good → auto-pass, critical → ask user.
    """
    from langgraph.types import interrupt
    from agents.api_analyzer import ApiAnalyzer

    state.setdefault("errors", [])

    if state.get("api_summary_confirmed"):
        return state

    interfaces = state.get("interfaces", [])
    api_raw_text = state.get("api_raw_text", "")
    api_summary = state.get("api_summary", [])
    feedback = state.get("api_summary_feedback", "")

    agent = ApiAnalyzer(_settings)

    print(f"\n[2/9] 分析接口文档...")

    if api_raw_text and not interfaces:
        print(f"  → ApiAnalyzer 正在从原文识别并分析接口 ({_settings.llm_model})...")
        if _sl():
            _sl().log_node_start("analyze_api", "2/9")
            _sl().log_event("llm_call", agent="ApiAnalyzer.analyze_raw_text",
                            model=_settings.llm_model, text_length=len(api_raw_text))
        if feedback:
            summary = agent.revise([], api_summary, feedback)
        else:
            summary = agent.analyze_raw_text(api_raw_text, Path(state.get("api_path", "")).name)
    else:
        print(f"  → ApiAnalyzer 正在调用 LLM ({_settings.llm_model})...")
        if _sl():
            _sl().log_node_start("analyze_api", "2/9")
        if feedback:
            summary = agent.revise(interfaces, api_summary, feedback)
        else:
            summary = agent.analyze(interfaces)

    print(f"  → 生成 {len(summary)} 个接口摘要")
    if _sl():
        _sl().log_node_end("analyze_api")

    state["api_summary"] = summary
    state["api_summary_feedback"] = ""

    memory_dir = state.get("memory_dir", "")
    if memory_dir:
        save_snapshot(memory_dir, "api_summary.json", summary)

    if api_raw_text and not interfaces:
        state["interfaces"] = summary_to_interfaces(summary)
        print(f"  → 从摘要重建 {len(state['interfaces'])} 个接口定义")

    critical = _has_critical_uncertainties(summary)

    if not critical:
        print("  → 未发现关键信息缺失，自动通过。")
        _print_api_summary_brief(summary)
        state["api_summary_confirmed"] = True
        return state

    print("\n  [接口分析] 发现以下不确定信息：")
    _print_uncertainties(summary)

    choice = interrupt("是否需要澄清以上问题？(输入修改意见 / 输入 skip 跳过): ")

    if choice.strip().lower() == "skip":
        state["api_summary_confirmed"] = True
    else:
        state["api_summary_feedback"] = choice

    return state


def _dispatch_rule_parser(api_path: str, parser_path: str = "") -> List[InterfaceDef]:
    """分发到合适的规则解析器。

    Dispatch to the appropriate rule-based parser.
    """
    if parser_path:
        return _load_custom_parser(parser_path)(api_path)

    ext = Path(api_path).suffix.lower()

    if ext in (".yaml", ".yml", ".json"):
        print(f"  → 使用 OpenApiParser 解析...")
        return OpenApiParser.parse(api_path)

    if ext in (".md", ".markdown"):
        print(f"  → 使用 MarkdownParser 解析...")
        return MarkdownParser.parse(api_path)

    try:
        print(f"  → 尝试 OpenApiParser...")
        interfaces = OpenApiParser.parse(api_path)
        if interfaces:
            return interfaces
    except Exception:
        pass

    try:
        print(f"  → 尝试 MarkdownParser...")
        interfaces = MarkdownParser.parse(api_path)
        if interfaces:
            return interfaces
    except Exception:
        pass

    return []


def _load_custom_parser(parser_path: str):
    """动态加载自定义解析器模块。

    Dynamically load a custom parser module and return its ``parse`` function.
    """
    path = Path(parser_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"自定义解析器未找到: {path}")

    spec = importlib.util.spec_from_file_location("custom_parser", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, "parse"):
        raise AttributeError(
            f"自定义解析器 {path} 必须实现 parse(file_path: str) -> List[InterfaceDef] 函数"
        )

    print(f"  → 使用自定义解析器: {path}")
    return module.parse


def _has_critical_uncertainties(summary: List[Dict]) -> bool:
    """检查摘要中是否有需要用户输入的关键未知项。

    Check if the summary has critical unknowns warranting user input.
    """
    for item in summary:
        if item.get("auth_type") == "不确定":
            return True
        if item.get("need_token") is None:
            return True
        if not item.get("description") or item.get("description") == "未知":
            return True
    return False


def _print_api_summary_brief(summary: List[Dict]) -> None:
    """打印紧凑的摘要表格。Print a compact summary table."""
    print("-" * 60)
    print(f"{'Endpoint':<30} {'Auth':<15} {'Need Token':<10}")
    print("-" * 60)
    for item in summary:
        path = item.get("api_path", "")[:28]
        method = item.get("method", "")
        auth = item.get("auth_type", "none")
        need_token = "Yes" if item.get("need_token") else "No"
        print(f"{method} {path:<27} {auth:<15} {need_token:<10}")
    print("-" * 60)


def _print_uncertainties(summary: List[Dict]) -> None:
    """仅打印有不确定项的条目。

    Print only items that have uncertainties.
    """
    for item in summary:
        uncertainties = item.get("uncertainties", [])
        if uncertainties:
            path = f"{item.get('method', '?')} {item.get('api_path', '?')}"
            print(f"\n  [{path}]")
            for u in uncertainties:
                print(f"    ? {u}")
