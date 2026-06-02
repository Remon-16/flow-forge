"""Workflow nodes — one function per stage in the main StateGraph."""

import logging
from typing import Any, Dict, List

from config.settings import Settings
from doc_parser.markdown_parser import MarkdownParser
from doc_parser.openapi_parser import OpenApiParser
from doc_parser.pdf_parser import PdfParser
from graph.state import GraphState
from knowledge.rag import RAGKnowledgeBase
from models.schema import InterfaceDef
from prompts.registry import PromptRegistry

logger = logging.getLogger(__name__)

# Module-level singletons (set by build_workflow and injected into nodes)
_settings: Settings = None
_prompt_registry: PromptRegistry = None
_rag: RAGKnowledgeBase = None


def configure(settings: Settings, prompt_registry: PromptRegistry, rag: RAGKnowledgeBase):
    """Wire module-level dependencies before building the graph."""
    global _settings, _prompt_registry, _rag
    _settings = settings
    _prompt_registry = prompt_registry
    _rag = rag


# =========================================================================
# Node: parse_docs
# =========================================================================
def parse_docs_node(state: GraphState) -> GraphState:
    """Read requirement files + API spec, store raw text and interfaces."""
    state.setdefault("errors", [])

    # --- Requirements ---
    requirement_text_parts: List[str] = []
    for path in state.get("requirement_paths", []):
        try:
            if path.lower().endswith((".txt", ".md")):
                with open(path, "r", encoding="utf-8") as f:
                    requirement_text_parts.append(f.read())
            elif path.lower().endswith(".pdf"):
                requirement_text_parts.append(PdfParser.parse(path))
            else:
                with open(path, "r", encoding="utf-8") as f:
                    requirement_text_parts.append(f.read())
        except Exception as e:
            msg = f"Failed to read requirement file '{path}': {e}"
            logger.error(msg)
            state["errors"].append(msg)

    state["requirement_text"] = "\n\n".join(requirement_text_parts)

    # --- API ---
    api_path = state.get("api_path", "")
    interfaces: List[InterfaceDef] = []
    try:
        if api_path.endswith((".yaml", ".yml", ".json")):
            interfaces = OpenApiParser.parse(api_path)
        elif api_path.endswith((".md", ".markdown")):
            interfaces = MarkdownParser.parse(api_path)
        else:
            # Try OpenAPI first, fallback to markdown
            try:
                interfaces = OpenApiParser.parse(api_path)
            except Exception:
                interfaces = MarkdownParser.parse(api_path)
    except Exception as e:
        msg = f"Failed to parse API doc '{api_path}': {e}"
        logger.error(msg)
        state["errors"].append(msg)

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

    if feedback:
        summary = agent.revise(interfaces, api_summary, feedback)
    else:
        summary = agent.analyze(interfaces)

    state["api_summary"] = summary
    state["api_summary_feedback"] = ""

    critical = _has_critical_uncertainties(summary)

    if not critical:
        print("\n[接口分析] 摘要已生成，未发现关键信息缺失，自动通过。")
        _print_api_summary_brief(summary)
        state["api_summary_confirmed"] = True
        return state

    print("\n[接口分析] 发现以下不确定信息：")
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

    agent = RequirementAnalyzer(_settings)
    # Inject prompt from registry if available, else agent uses its own defaults
    result = agent.analyze(text)
    state["requirement_analysis"] = result
    return state


# =========================================================================
# Node: generate_plan
# =========================================================================
def generate_plan_node(state: GraphState) -> GraphState:
    """Generate a test plan markdown from requirement analysis + interfaces."""
    from agents.plan_generator import PlanGenerator

    state.setdefault("errors", [])

    agent = PlanGenerator(_settings)

    analysis = state.get("requirement_analysis", {})
    interfaces = state.get("interfaces", [])

    api_summary = state.get("api_summary", [])
    plan_md = agent.generate(analysis, interfaces, api_summary=api_summary)
    state["plan_md"] = plan_md
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

    # Show a short summary
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

    # Pause and wait for human decision
    decision = interrupt("请审核测试计划")

    # decision is str: "approved" or the feedback text
    if decision == "approved":
        state["plan_confirmed"] = True
        state["plan_feedback"] = ""
    else:
        state["plan_confirmed"] = False
        state["plan_feedback"] = decision

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

    print("\n  正在根据反馈修改计划...")
    revised = agent.call_llm(prompt, system)
    state["plan_md"] = revised
    state["plan_feedback"] = ""  # Clear for next round

    return state


# =========================================================================
# Node: parse_plan
# =========================================================================
def parse_plan_node(state: GraphState) -> GraphState:
    """Parse the confirmed plan.md into a structured TestPlan."""
    from agents.plan_parser import PlanParser

    state.setdefault("errors", [])
    plan_md = state.get("plan_md", "")

    agent = PlanParser(_settings)
    plan = agent.parse(plan_md)

    # Store in state for downstream use
    state["plan_parsed"] = plan  # type: ignore[typeddict-unknown-key]
    return state


# =========================================================================
# Node: generate_cases
# =========================================================================
def generate_cases_node(state: GraphState) -> GraphState:
    """Generate concrete test cases from the structured plan + interfaces."""
    from agents.case_generator import CaseGenerator

    state.setdefault("errors", [])

    agent = CaseGenerator(_settings)
    plan = state.get("plan_parsed")
    interfaces = state.get("interfaces", [])

    single_cases, biz_flows = agent.generate(plan, interfaces)
    state["single_cases"] = single_cases
    state["biz_flows"] = biz_flows
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

    try:
        ExcelWriter.write(interfaces, single, biz, output)
    except Exception as e:
        msg = f"Failed to write Excel: {e}"
        logger.error(msg)
        state["errors"].append(msg)

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
