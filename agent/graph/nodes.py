"""Workflow nodes — one function per stage in the main StateGraph."""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from config.settings import Settings
from doc_parser.markdown_parser import MarkdownParser
from doc_parser.openapi_parser import OpenApiParser
from doc_parser.pdf_parser import PdfParser
from graph.state import GraphState
from knowledge.search import KnowledgeSearch
from models.schema import InterfaceDef
from prompts.registry import PromptRegistry

logger = logging.getLogger(__name__)

# Module-level singletons (set by build_workflow and injected into nodes)
_settings: Settings = None
_prompt_registry: PromptRegistry = None
_knowledge: Optional[KnowledgeSearch] = None
_session_logger = None


def configure(
    settings: Settings,
    prompt_registry: PromptRegistry,
    knowledge: Optional[KnowledgeSearch],
    session_logger=None,
):
    """Wire module-level dependencies before building the graph."""
    global _settings, _prompt_registry, _knowledge, _session_logger
    _settings = settings
    _prompt_registry = prompt_registry
    _knowledge = knowledge
    _session_logger = session_logger

    # Wire grep_knowledge tool if knowledge is available
    from tools.builtin import set_knowledge_instance
    set_knowledge_instance(knowledge)


def _sl():
    """Shorthand to get the session logger (may be None)."""
    return _session_logger


def _fmt_size(path: str) -> str:
    """Format file size for display."""
    try:
        size = Path(path).stat().st_size
        if size >= 1024:
            return f"{size / 1024:.1f} KB"
        return f"{size} B"
    except OSError:
        return "? B"


# =========================================================================
# Node: parse_docs
# =========================================================================
def parse_docs_node(state: GraphState) -> GraphState:
    """Read requirement files + API spec, store raw text and interfaces."""
    state.setdefault("errors", [])

    print("\n[1/8] 读取文档...")

    # --- Requirements ---
    requirement_text_parts: List[str] = []
    for path in state.get("requirement_paths", []):
        size_str = _fmt_size(path)
        ext = Path(path).suffix.lower()
        try:
            if ext in (".txt", ".md"):
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                    requirement_text_parts.append(content)
                print(f"  → 读取 {path} ({size_str})")
                if _sl():
                    _sl().log_file_read(path, len(content))
            elif ext == ".pdf":
                content = PdfParser.parse(path)
                requirement_text_parts.append(content)
                print(f"  → 解析 {path} ({size_str}, PDF)")
                if _sl():
                    _sl().log_file_read(path, len(content))
            else:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                    requirement_text_parts.append(content)
                print(f"  → 读取 {path} ({size_str})")
                if _sl():
                    _sl().log_file_read(path, len(content))
        except Exception as e:
            msg = f"Failed to read requirement file '{path}': {e}"
            logger.error(msg)
            state["errors"].append(msg)
            print(f"  ✗ {msg}")

    state["requirement_text"] = "\n\n".join(requirement_text_parts)

    # --- API ---
    api_path = state.get("api_path", "")
    interfaces: List[InterfaceDef] = []
    if api_path:
        size_str = _fmt_size(api_path)
        try:
            if api_path.endswith((".yaml", ".yml", ".json")):
                interfaces = OpenApiParser.parse(api_path)
                print(f"  → 解析 {api_path} (OpenAPI, {size_str}, {len(interfaces)} 个接口)")
            elif api_path.endswith((".md", ".markdown")):
                interfaces = MarkdownParser.parse(api_path)
                print(f"  → 解析 {api_path} (Markdown, {size_str}, {len(interfaces)} 个接口)")
            else:
                # Try OpenAPI first, fallback to markdown
                try:
                    interfaces = OpenApiParser.parse(api_path)
                    print(f"  → 解析 {api_path} (OpenAPI, {size_str}, {len(interfaces)} 个接口)")
                except Exception:
                    interfaces = MarkdownParser.parse(api_path)
                    print(f"  → 解析 {api_path} (Markdown, {size_str}, {len(interfaces)} 个接口)")
            if _sl():
                _sl().log_file_read(api_path, Path(api_path).stat().st_size)
        except Exception as e:
            msg = f"Failed to parse API doc '{api_path}': {e}"
            logger.error(msg)
            state["errors"].append(msg)
            print(f"  ✗ {msg}")

    state["interfaces"] = [_iface_to_dict(i) for i in interfaces]
    return state


# =========================================================================
# Node: analyze_api — API doc analysis with optional human-in-the-loop
# =========================================================================
def analyze_api_node(state: GraphState) -> GraphState:
    """Analyze API docs and generate structured summaries.

    Self-evaluates quality:
    - Good quality → auto-pass, continue to next node
    - Critical uncertainties → optionally ask user for clarification
    """
    from langgraph.types import interrupt

    from agents.api_analyzer import ApiAnalyzer

    state.setdefault("errors", [])

    # Already confirmed — skip
    if state.get("api_summary_confirmed"):
        return state

    interfaces = state.get("interfaces", [])
    api_summary = state.get("api_summary", [])
    feedback = state.get("api_summary_feedback", "")

    agent = ApiAnalyzer(_settings)

    print(f"\n[2/8] 分析接口文档...")
    print(f"  → ApiAnalyzer 正在调用 LLM ({_settings.llm_model})...")
    if _sl():
        _sl().log_node_start("analyze_api", "2/8")

    if feedback:
        summary = agent.revise(interfaces, api_summary, feedback)
    else:
        summary = agent.analyze(interfaces)

    print(f"  → 生成 {len(summary)} 个接口摘要")
    if _sl():
        _sl().log_node_end("analyze_api")

    state["api_summary"] = summary
    state["api_summary_feedback"] = ""

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


def _has_critical_uncertainties(summary: List[Dict]) -> bool:
    """Check if the summary has any critical unknowns that warrant user input."""
    for item in summary:
        if item.get("auth_type") == "不确定":
            return True
        if item.get("need_token") is None:
            return True
        if not item.get("description") or item.get("description") == "未知":
            return True
    return False


def _print_api_summary_brief(summary: List[Dict]) -> None:
    """Print a compact summary table to the console."""
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
    """Print only the items that have uncertainties."""
    for item in summary:
        uncertainties = item.get("uncertainties", [])
        if uncertainties:
            path = f"{item.get('method', '?')} {item.get('api_path', '?')}"
            print(f"\n  [{path}]")
            for u in uncertainties:
                print(f"    ? {u}")


# =========================================================================
# Node: analyze_requirement
# =========================================================================
def analyze_requirement_node(state: GraphState) -> GraphState:
    """Run the requirement analyzer (single-shot LLM call for MVP, ReAct-ready)."""
    from agents.requirement_analyzer import RequirementAnalyzer

    state.setdefault("errors", [])

    text = state.get("requirement_text", "")
    if not text.strip():
        state["requirement_analysis"] = {
            "business_flows": [],
            "roles": [],
            "constraints": [],
            "exceptions": [],
        }
        return state

    print(f"\n[3/8] 分析需求文档...")
    print(f"  → RequirementAnalyzer 正在调用 LLM ({_settings.llm_model})...")
    if _sl():
        _sl().log_node_start("analyze_requirement", "3/8")

    agent = RequirementAnalyzer(_settings, _knowledge)
    result = agent.analyze(text)
    state["requirement_analysis"] = result

    flows = len(result.get("business_flows", []))
    roles = len(result.get("roles", []))
    print(f"  → 提取 {flows} 个业务流程, {roles} 个角色")
    if _sl():
        _sl().log_node_end("analyze_requirement")

    return state


# =========================================================================
# Node: generate_plan
# =========================================================================
def generate_plan_node(state: GraphState) -> GraphState:
    """Generate a test plan markdown from requirement analysis + interfaces."""
    from agents.plan_generator import PlanGenerator

    state.setdefault("errors", [])

    agent = PlanGenerator(_settings, _knowledge)

    analysis = state.get("requirement_analysis", {})
    interfaces = state.get("interfaces", [])
    api_summary = state.get("api_summary", [])
    user_guidance = state.get("user_guidance", "")

    print(f"\n[4/8] 生成测试计划...")
    print(f"  → PlanGenerator 正在调用 LLM ({_settings.llm_model})...")
    if _sl():
        _sl().log_node_start("generate_plan", "4/8")

    plan_md = agent.generate(
        analysis,
        interfaces,
        api_summary=api_summary,
        user_guidance=user_guidance,
    )
    state["plan_md"] = plan_md

    plan_len = len(plan_md)

    # Write plan to session directory if available
    if _sl():
        plan_path = _sl().save_plan(plan_md)
        print(f"  → 计划已生成 ({plan_len} 字符)，已保存至 {plan_path}")
    else:
        print(f"  → 计划已生成 ({plan_len} 字符)")

    if _sl():
        _sl().log_node_end("generate_plan")

    return state


# =========================================================================
# Node: human_confirm (interrupt point)
# =========================================================================
def human_confirm_node(state: GraphState) -> GraphState:
    """Interrupt point — pauses execution for human review of the plan.

    Uses LangGraph ``interrupt()`` to pause. The CLI catches the interrupt,
    prompts the user, and resumes with either approval or feedback.
    """
    from langgraph.types import interrupt

    plan_md = state.get("plan_md", "")
    feedback = state.get("plan_feedback", "")

    print("\n" + "=" * 60)
    if feedback:
        print("  [修改后计划] 已根据您的反馈修改测试计划：")
        print(f"  修改意见: {feedback}")
    else:
        print("  [新生成的测试计划]")
    print("=" * 60)
    preview = plan_md[:500] + ("..." if len(plan_md) > 500 else "")
    print(preview)
    print("=" * 60)
    if _sl():
        _sl().log_node_start("human_confirm", "5/8")

    # Pause and wait for human decision
    decision = interrupt("请审核测试计划")

    # decision is str: "approved" or the feedback text
    if decision == "approved":
        state["plan_confirmed"] = True
        state["plan_feedback"] = ""
    else:
        state["plan_confirmed"] = False
        state["plan_feedback"] = decision

    if _sl():
        _sl().log_node_end("human_confirm")

    return state


# =========================================================================
# Node: revise_plan
# =========================================================================
def revise_plan_node(state: GraphState) -> GraphState:
    """Revise the plan based on user feedback, then return to human_confirm."""
    from agents.base import BaseAgent
    from prompts.render import render_prompt

    feedback = state.get("plan_feedback", "")
    plan_md = state.get("plan_md", "")
    analysis = state.get("requirement_analysis", {})
    api_summary = state.get("api_summary", [])

    if not feedback.strip():
        logger.warning("revise_plan called without feedback, skipping")
        return state

    agent = BaseAgent(
        api_key=_settings.llm_api_key,
        model=_settings.llm_model,
        temperature=0.3,
        max_tokens=_settings.llm_max_tokens,
        base_url=_settings.llm_base_url,
    )

    # Build system prompt from registry if plan_reviser exists
    system = _prompt_registry.get_system("plan_reviser")
    if not system:
        system = (
            "你是一个专业的测试计划修改专家。请根据用户的反馈修改测试计划，"
            "同时保持原始计划中用户未提及部分不变。"
            "修改后的计划应保持完整的结构：业务理解、单接口测试点、业务链路测试、Mermaid 流程图。"
            "使用中文编写。"
        )

    user_msg = _prompt_registry.get_user_template("plan_reviser")
    if not user_msg:
        user_msg = (
            "## 原始测试计划\n{{original_plan}}\n\n"
            "## 用户修改意见\n{{feedback}}\n\n"
            "## 需求分析结果（参考）\n```json\n{{requirement_analysis}}\n```\n\n"
            "## 接口分析摘要\n```json\n{{api_summary}}\n```\n\n"
            "请生成修改后的完整测试计划。"
        )

    prompt = render_prompt(
        user_msg,
        original_plan=plan_md,
        feedback=feedback,
        requirement_analysis=str(analysis),
        api_summary=str(api_summary),
    )

    print(f"\n  → PlanReviser 正在调用 LLM ({_settings.llm_model})...")
    revised = agent.call_llm(prompt, system)
    state["plan_md"] = revised
    state["plan_feedback"] = ""  # Clear for next round

    # Overwrite plan.md in session directory
    if _sl():
        _sl().save_plan(revised)

    return state


# =========================================================================
# Node: parse_plan
# =========================================================================
def parse_plan_node(state: GraphState) -> GraphState:
    """Parse the confirmed plan.md into a structured TestPlan."""
    from agents.plan_parser import PlanParser

    state.setdefault("errors", [])
    plan_md = state.get("plan_md", "")

    print(f"\n[6/8] 解析测试计划...")
    print(f"  → PlanParser 正在调用 LLM ({_settings.llm_model})...")
    if _sl():
        _sl().log_node_start("parse_plan", "6/8")

    agent = PlanParser(_settings)
    plan = agent.parse(plan_md)

    state["plan_parsed"] = plan

    api_count = len(plan.api_definitions)
    tp_count = sum(len(v) for v in plan.single_test_points.values())
    print(f"  → 解析完成 ({api_count} 个接口定义, {tp_count} 个测试点)")
    if _sl():
        _sl().log_node_end("parse_plan")

    return state


# =========================================================================
# Node: generate_cases
# =========================================================================
def generate_cases_node(state: GraphState) -> GraphState:
    """Generate concrete test cases from the structured plan + interfaces."""
    from agents.case_generator import CaseGenerator

    state.setdefault("errors", [])

    agent = CaseGenerator(_settings, _knowledge)
    plan = state.get("plan_parsed")
    interfaces = state.get("interfaces", [])
    user_guidance = state.get("user_guidance", "")

    print(f"\n[7/8] 生成测试用例...")
    print(f"  → CaseGenerator 正在调用 LLM ({_settings.llm_model})...")
    if _sl():
        _sl().log_node_start("generate_cases", "7/8")

    result = agent.generate(plan, interfaces, user_guidance=user_guidance)
    single_cases = result.get("single_cases", [])
    biz_flows = result.get("biz_flows", [])

    state["single_cases"] = single_cases
    state["biz_flows"] = biz_flows

    print(f"  → 生成 {len(single_cases)} 条单接口用例, {len(biz_flows)} 条业务链路")
    if _sl():
        _sl().log_node_end("generate_cases")

    return state


# =========================================================================
# Node: write_excel
# =========================================================================
def write_excel_node(state: GraphState) -> GraphState:
    """Write the final test case Excel file."""
    from agents.excel_writer import ExcelWriter

    state.setdefault("errors", [])

    output = state.get("output_path", "test_cases.xlsx")
    interfaces = state.get("interfaces", [])
    single = state.get("single_cases", [])
    biz = state.get("biz_flows", [])

    print(f"\n[8/8] 写入 Excel...")
    if _sl():
        _sl().log_node_start("write_excel", "8/8")

    try:
        ExcelWriter.write(interfaces, single, biz, output)
        print(f"  → 写入 {output}")

        # Copy to session directory
        if _sl():
            excel_copy = _sl().save_excel(output)
            if excel_copy:
                print(f"  → 已备份至 {excel_copy}")

        sheet_count = 2 + len(biz)
        print(f"  → 共 {sheet_count} 个 Sheet (接口定义 + {len(single)} 条单接口用例 + {len(biz)} 条业务链路)")
    except Exception as e:
        msg = f"Failed to write Excel: {e}"
        logger.error(msg)
        state["errors"].append(msg)
        print(f"  ✗ {msg}")

    if _sl():
        _sl().log_node_end("write_excel")

    return state


# =========================================================================
# Edge logic (in nodes module to keep it simple)
# =========================================================================
def check_confirmed(state: GraphState) -> str:
    """Conditional edge after human_confirm_node.

    Returns:
        "confirmed" → proceed to parse_plan
        "rejected" → route to revise_plan for modification
    """
    if state.get("plan_confirmed"):
        return "confirmed"
    return "rejected"


def route_after_api_confirm(state: GraphState) -> str:
    """Conditional edge after analyze_api_node.

    Returns:
        "next" → proceed to analyze_requirement
        "loop" → stay on analyze_api for revision
    """
    if state.get("api_summary_confirmed"):
        return "next"
    return "loop"


# =========================================================================
# Helpers
# =========================================================================
def _iface_to_dict(i: InterfaceDef) -> Dict[str, Any]:
    return {
        "test_id": i.test_id,
        "api_name": i.api_name,
        "app_name": i.app_name,
        "method": i.method,
        "url": i.url,
        "request_head": i.request_head,
        "request_body": i.request_body,
        "status_code": i.status_code,
        "assert_dict": i.assert_dict,
        "remark": i.remark,
    }
