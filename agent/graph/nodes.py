"""Workflow nodes — one function per stage in the main StateGraph."""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from config.settings import Settings
from doc_parser.llm_parser import DocParserAgent
from doc_parser.markdown_parser import MarkdownParser
from doc_parser.openapi_parser import OpenApiParser
from doc_parser.pdf_parser import PdfParser
from doc_parser.text_extractor import extract_text
from graph.state import GraphState
from knowledge.search import KnowledgeSearch
from models.schema import InterfaceDef, PlanStep, TestPlan
from prompts.registry import PromptRegistry
from writers.yaml_writer import YamlWriter

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


def _summarize_reference_dir(reference_dir: str) -> str:
    """Scan reference directory for existing test assets and return a
    summary suitable for injecting into the plan generation prompt.

    Returns "(无)" if the directory is empty or invalid.
    """
    if not reference_dir:
        return "(无)"

    ref_path = Path(reference_dir)
    parts = []

    # 1. Existing plan
    plan_path = ref_path / "plan.md"
    if plan_path.exists():
        try:
            plan_text = plan_path.read_text(encoding="utf-8")
            parts.append(f"### 已有测试计划\n{plan_text[:5000]}")
        except Exception:
            pass

    # 2. Existing interfaces
    try:
        ifaces = YamlWriter.read_interfaces(reference_dir)
        if ifaces:
            lines = [
                f"- {i.get('test_id', '?')}: {i.get('method', 'GET')} {i.get('url', '')}"
                for i in ifaces
            ]
            parts.append(f"### 已有接口 ({len(ifaces)} 个)\n" + "\n".join(lines))
    except Exception:
        pass

    # 3. Existing single cases
    try:
        cases = YamlWriter.read_single_cases(reference_dir)
        if cases:
            ids = [str(c.get("test_id", "?")) for c in cases]
            parts.append(
                f"### 已生成单接口用例 ({len(cases)} 个)\n"
                f"覆盖: {', '.join(ids[:50])}"
            )
    except Exception:
        pass

    # 4. Existing biz flows
    try:
        flows = YamlWriter.read_biz_flows(reference_dir)
        if flows:
            names = [str(f.get("sheet_name", "?")) for f in flows]
            parts.append(
                f"### 已生成业务链路用例 ({len(flows)} 个)\n"
                f"{', '.join(names[:20])}"
            )
    except Exception:
        pass

    if not parts:
        return "(参考目录为空或无法读取)"

    parts.append(
        "\n请仅对新增或变更的接口和场景进行测试规划。"
        "已覆盖且未变更的部分无需重复，可在计划中标注'已覆盖'。"
    )
    return "\n\n".join(parts)


# =========================================================================
# Node: parse_docs
# =========================================================================
def parse_docs_node(state: GraphState) -> GraphState:
    """Read requirement files + API spec.

    Three parse modes (from ``state["parse_mode"]``):
    - ``raw`` (default): Extract text, store in api_raw_text. Defer analysis.
    - ``rule``: Use rule-based parsers (OpenAPI / Markdown / custom).
    - ``llm``: Use DocParserAgent (LLM) to pre-extract structured interfaces.
    """
    state.setdefault("errors", [])

    print("\n[1/9] 读取文档...")

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
    parse_mode = state.get("parse_mode", "raw")
    state["interfaces_from_llm"] = False

    if not api_path:
        state["interfaces"] = []
        state["interface_extraction_method"] = "none"
        return state

    size_str = _fmt_size(api_path)
    ext = Path(api_path).suffix.lower()

    print(f"  → 解析模式: {parse_mode}")

    if parse_mode == "raw":
        # ---- Raw mode: extract text, pass to analyze_api_node ----
        raw_text = extract_text(api_path)
        if not raw_text.strip():
            raise Exception(f"API 文档 '{api_path}' 内容为空，无法解析。")

        state["api_raw_text"] = raw_text
        state["interfaces"] = []
        state["interface_extraction_method"] = "raw"
        print(f"  → 读取 API 文档原文 ({size_str}, {len(raw_text)} 字符)")
        print(f"  → 接口识别将在下一步由 ApiAnalyzer 完成")

    elif parse_mode == "rule":
        # ---- Rule mode: built-in or custom parser ----
        interfaces = _dispatch_rule_parser(api_path, state.get("parser_path", ""))
        if len(interfaces) == 0:
            raise Exception(
                f"规则解析器未从 '{api_path}' 提取到接口。\n"
                f"建议：\n"
                f"  1. 尝试 --parse-mode raw（默认，让 LLM 直接从原文识别接口）\n"
                f"  2. 尝试 --parse-mode llm（用 LLM 预提取结构化接口）\n"
                f"  3. 编写自定义解析器: --parser-path /path/to/parser.py"
            )
        state["interfaces"] = [_iface_to_dict(i) for i in interfaces]
        state["interface_extraction_method"] = "rule"
        print(f"  → 规则解析完成 ({len(interfaces)} 个接口)")

    elif parse_mode == "llm":
        # ---- LLM mode: pre-extract structured interfaces ----
        raw_text = extract_text(api_path)
        if not raw_text.strip():
            raise Exception(f"API 文档 '{api_path}' 内容为空，无法解析。")

        print(f"  → 读取 API 文档原文 ({size_str}, {len(raw_text)} 字符)")
        print(f"  → DocParserAgent 正在调用 LLM ({_settings.llm_model}) 提取接口...")
        if _sl():
            _sl().log_event("llm_call", agent="DocParserAgent", model=_settings.llm_model,
                            text_length=len(raw_text))

        parser = DocParserAgent(_settings)
        interfaces = parser.parse(
            raw_text=raw_text,
            file_name=Path(api_path).name,
            file_type_hint=ext,
        )

        if len(interfaces) == 0:
            raise Exception(
                f"LLM 未从 '{api_path}' 提取到接口。\n"
                f"建议：\n"
                f"  1. 尝试 --parse-mode raw（让 ApiAnalyzer 直接从原文分析）\n"
                f"  2. 检查文件内容是否描述了 API 接口"
            )

        state["interfaces"] = [_iface_to_dict(i) for i in interfaces]
        state["interfaces_from_llm"] = True
        state["interface_extraction_method"] = "llm"
        print(f"  → LLM 成功提取 {len(interfaces)} 个接口")

    else:
        raise Exception(
            f"未知的解析模式: {parse_mode}。"
            f"支持的模式: raw (默认), rule, llm"
        )

    if _sl():
        _sl().log_file_read(api_path, Path(api_path).stat().st_size)

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
    api_raw_text = state.get("api_raw_text", "")
    api_summary = state.get("api_summary", [])
    feedback = state.get("api_summary_feedback", "")

    agent = ApiAnalyzer(_settings)

    print(f"\n[2/9] 分析接口文档...")

    if api_raw_text and not interfaces:
        # Raw mode: analyze directly from text
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
        # Rule/llm mode: analyze from structured interfaces
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

    # In raw mode, reconstruct interfaces from the summary so downstream
    # nodes (generate_cases, write_excel) have interface definitions.
    if api_raw_text and not interfaces:
        state["interfaces"] = _summary_to_interfaces(summary)
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
    """Dispatch to the appropriate rule-based parser.

    If ``parser_path`` is set, dynamically load and call the custom parser's
    ``parse(file_path) -> List[InterfaceDef]`` function.
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

    # Unknown extension: try OpenAPI first, then Markdown
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
    """Dynamically load a custom parser module and return its ``parse`` function."""
    import importlib.util
    from pathlib import Path

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

    print(f"\n[3/9] 分析需求文档...")
    print(f"  → RequirementAnalyzer 正在调用 LLM ({_settings.llm_model})...")
    if _sl():
        _sl().log_node_start("analyze_requirement", "3/9")

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
    """Generate a test plan markdown from requirement analysis + interfaces.

    When ``state["reference_dir"]`` is set, scans that directory for existing
    plans, interfaces, and cases, and injects a summary into the LLM prompt
    so that the plan can be generated incrementally.
    """
    from agents.plan_generator import PlanGenerator

    state.setdefault("errors", [])

    # Build reference summary for incremental updates
    reference_dir = state.get("reference_dir", "")
    reference_summary = _summarize_reference_dir(reference_dir)

    agent = PlanGenerator(_settings, _knowledge)

    analysis = state.get("requirement_analysis", {})
    interfaces = state.get("interfaces", [])
    api_summary = state.get("api_summary", [])
    user_guidance = state.get("user_guidance", "")

    if reference_dir:
        print(f"\n[4/9] 生成测试计划 (增量模式)...")
        print(f"  → 参考目录: {reference_dir}")
    else:
        print(f"\n[4/9] 生成测试计划...")
    print(f"  → PlanGenerator 正在调用 LLM ({_settings.llm_model})...")
    if _sl():
        _sl().log_node_start("generate_plan", "4/9")

    plan_md = agent.generate(
        analysis,
        interfaces,
        api_summary=api_summary,
        user_guidance=user_guidance,
        reference_summary=reference_summary,
    )
    state["plan_md"] = plan_md

    plan_len = len(plan_md)

    # Save plan.md to output_dir (in addition to session dir)
    output_dir = state.get("output_dir", "./output")
    try:
        plan_path = Path(output_dir) / "plan.md"
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(plan_md, encoding="utf-8")
    except Exception as e:
        logger.warning("Failed to save plan.md to output_dir: %s", e)

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

    print(f"\n[5/9] 审核测试计划...")
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
        _sl().log_node_start("human_confirm", "5/9")

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

    print(f"\n[6/9] 解析测试计划...")
    print(f"  → PlanParser 正在调用 LLM ({_settings.llm_model})...")
    if _sl():
        _sl().log_node_start("parse_plan", "6/9")

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
    interfaces_raw = state.get("interfaces", [])
    user_guidance = state.get("user_guidance", "")

    print(f"\n[7/8] 生成测试用例...")
    print(f"  → CaseGenerator 正在调用 LLM ({_settings.llm_model})...")
    if _sl():
        _sl().log_node_start("generate_cases", "7/8")

    interfaces = _dicts_to_interfaces(interfaces_raw)
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
# Node: save_interfaces
# =========================================================================
def save_interfaces_node(state: GraphState) -> GraphState:
    """Save parsed interface definitions as YAML files in output_dir/interfaces/."""
    from pathlib import Path

    from writers.yaml_writer import YamlWriter

    state.setdefault("errors", [])

    print(f"\n[7/9] 保存接口定义...")
    if _sl():
        _sl().log_node_start("save_interfaces", "7/9")

    interfaces = state.get("interfaces", [])
    output_dir = state.get("output_dir", "./output")

    if not interfaces:
        logger.warning("No interfaces to save")
        return state

    interfaces_dir = Path(output_dir) / "interfaces"
    interfaces_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for iface in interfaces:
        try:
            YamlWriter.write_interface(iface, output_dir)
            count += 1
        except Exception as e:
            logger.warning("Failed to save interface: %s", e)

    print(f"\n  → 保存 {count} 个接口定义到 {interfaces_dir}")
    if _sl():
        _sl().log_event("save_interfaces", count=count, dir=str(interfaces_dir))
        _sl().log_node_end("save_interfaces")

    return state


# =========================================================================
# Node: batch_controller
# =========================================================================
def batch_controller_node(state: GraphState) -> GraphState:
    """Run three-step test case generation pipeline.

    Step 1: Skeleton generation (one-shot, no batching)
    Step 2: Data filling (code-based batching)
    Step 3: Assertion generation (code-based batching)

    In resume mode (state["resume"] is True), builds a minimal TestPlan
    from existing interface YAMLs when no structured plan is available.
    """
    from agents.batch_controller import BatchController
    from agents.skeleton_generator import SingleSkeletonGenerator, BizSkeletonGenerator
    from agents.data_filler import SingleDataFiller, BizDataFiller
    from agents.assertion_generator import SingleAssertionGenerator, BizAssertionGenerator
    from validators.case_validator import CaseValidator

    state.setdefault("errors", [])

    plan = state.get("plan_parsed")
    interfaces_raw = state.get("interfaces", [])
    output_dir = state.get("output_dir", "./output")
    user_guidance = state.get("user_guidance", "")
    batch_size = state.get("batch_size", _settings.batch_size)
    enable_validation = state.get("enable_validation", _settings.enable_validation)
    max_retries = state.get("max_validation_retries", _settings.max_validation_retries)
    reference_dir = state.get("reference_dir", "")
    api_summary = state.get("api_summary", [])

    # Resume mode: build minimal TestPlan from existing interface YAMLs
    if state.get("resume") and (plan is None or not interfaces_raw):
        existing_ifaces = YamlWriter.read_interfaces(output_dir)
        if not interfaces_raw:
            interfaces_raw = existing_ifaces
        if plan is None:
            single_tps = {}
            for iface in existing_ifaces:
                tid = iface.get("test_id", "")
                if tid:
                    single_tps[tid] = [
                        PlanStep(
                            test_id=f"{tid}_positive",
                            description="正向场景", tag="P0",
                            scenario_type="positive"),
                        PlanStep(
                            test_id=f"{tid}_negative",
                            description="负向场景", tag="P1",
                            scenario_type="negative"),
                        PlanStep(
                            test_id=f"{tid}_boundary",
                            description="边界场景", tag="P2",
                            scenario_type="boundary"),
                    ]
            plan = TestPlan(
                business_summary="Resume mode — minimal plan from existing interfaces",
                single_test_points=single_tps,
            )
        state["plan_parsed"] = plan
        state["interfaces"] = interfaces_raw

    print(f"\n[8/10] 三步测试用例生成...")
    print(f"  → 步骤1: 骨架生成 | 步骤2: 数据填充 | 步骤3: 断言生成")
    print(f"  → batch_size={batch_size}, validation={enable_validation}")
    if _sl():
        _sl().log_node_start("batch_controller", "8/10")

    # Create 6 specialized agents (single vs biz for each step)
    single_skel_gen = SingleSkeletonGenerator(_settings, _knowledge)
    biz_skel_gen = BizSkeletonGenerator(_settings, _knowledge)
    single_data_filler = SingleDataFiller(_settings, _knowledge)
    biz_data_filler = BizDataFiller(_settings, _knowledge)
    single_assert_gen = SingleAssertionGenerator(_settings, _knowledge)
    biz_assert_gen = BizAssertionGenerator(_settings, _knowledge)
    validator = CaseValidator(_settings) if enable_validation else None

    controller = BatchController(_settings)
    controller._batch_size = batch_size
    controller._enable_validation = enable_validation
    controller._max_validation_retries = max_retries

    interfaces = _dicts_to_interfaces(interfaces_raw)

    # Get original API doc text for URL existence validation
    api_path = state.get("api_path", "")
    api_doc_text = state.get("api_raw_text", "")
    if not api_doc_text and api_path:
        from doc_parser.text_extractor import extract_text
        try:
            api_doc_text = extract_text(api_path)
        except Exception:
            api_doc_text = ""

    try:
        result = controller.run(
            plan=plan,
            interfaces=interfaces_raw,
            output_dir=output_dir,
            single_skel_gen=single_skel_gen,
            biz_skel_gen=biz_skel_gen,
            single_data_filler=single_data_filler,
            biz_data_filler=biz_data_filler,
            single_assert_gen=single_assert_gen,
            biz_assert_gen=biz_assert_gen,
            validator=validator,
            user_guidance=user_guidance,
            reference_dir=reference_dir,
            api_doc_text=api_doc_text,
            api_summary=api_summary,
        )
    except Exception as e:
        msg = f"BatchController failed: {e}"
        logger.exception(msg)
        state["errors"].append(msg)
        print(f"  ✗ {msg}")
        state["single_cases"] = []
        state["biz_flows"] = []
        state["validation_failures"] = []
        return state

    single_cases = result.get("single_cases", [])
    biz_flows = result.get("biz_flows", [])
    failures = result.get("failures", [])

    state["single_cases"] = single_cases
    state["biz_flows"] = biz_flows
    state["validation_failures"] = failures

    print(f"  → 生成 {len(single_cases)} 条单接口用例, {len(biz_flows)} 条业务链路")
    if failures:
        print(f"  → {len(failures)} 个用例生成失败 (详见 {output_dir}/failures.yaml)")

    if _sl():
        _sl().log_node_end("batch_controller")

    return state


# =========================================================================
# Node: write_output
# =========================================================================
def write_output_node(state: GraphState) -> GraphState:
    """Write final output: YAML is already saved; optionally convert to Excel."""
    from agents.excel_writer import ExcelWriter

    state.setdefault("errors", [])

    output_format = state.get("output_format", "both")
    output_dir = state.get("output_dir", "./output")
    output_path = state.get("output_path", "test_cases.xlsx")
    single = state.get("single_cases", [])
    biz = state.get("biz_flows", [])
    failures = state.get("validation_failures", [])

    print(f"\n[9/9] 写入输出...")
    if _sl():
        _sl().log_node_start("write_output", "9/9")

    if output_format in ("excel", "both"):
        try:
            ExcelWriter.yaml_to_excel(output_dir, output_path)
            print(f"  → Excel 已写入 {output_path}")

            if _sl():
                excel_copy = _sl().save_excel(output_path)
                if excel_copy:
                    print(f"  → 已备份至 {excel_copy}")
        except Exception as e:
            msg = f"Failed to write Excel: {e}"
            logger.error(msg)
            state["errors"].append(msg)
            print(f"  ✗ {msg}")

    if output_format in ("yaml", "both"):
        print(f"  → YAML 用例已保存到 {output_dir}")
        print(f"     interfaces/: {_count_yaml(output_dir, 'interfaces')} 个")
        print(f"     single_cases/: {_count_yaml(output_dir, 'single_cases')} 个")
        print(f"     biz_flows/: {_count_yaml(output_dir, 'biz_flows')} 个")

    if failures:
        print(f"  → 校验失败: {len(failures)} 个 (详见 {output_dir}/failures.yaml)")

    if _sl():
        _sl().log_node_end("write_output")

    return state


def _count_yaml(output_dir: str, subdir: str) -> int:
    from pathlib import Path
    p = Path(output_dir) / subdir
    return len(list(p.glob("*.yaml"))) if p.is_dir() else 0


# =========================================================================
# Node: write_excel (legacy — kept for backward compatibility)
# =========================================================================
def write_excel_node(state: GraphState) -> GraphState:
    """Write the final test case Excel file (legacy single-shot mode)."""
    from agents.excel_writer import ExcelWriter

    state.setdefault("errors", [])

    output = state.get("output_path", "test_cases.xlsx")
    interfaces_raw = state.get("interfaces", [])
    single = state.get("single_cases", [])
    biz = state.get("biz_flows", [])

    print(f"\n[8/8] 写入 Excel...")
    if _sl():
        _sl().log_node_start("write_excel", "8/8")

    interfaces = _dicts_to_interfaces(interfaces_raw)

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


def _summary_to_interfaces(summary: List[Dict]) -> List[Dict[str, Any]]:
    """将 ApiAnalyzer 返回的摘要字典列表转换为 InterfaceDef 字典列表。

    api_summary 字段 → InterfaceDef 字段映射：
    - api_path → url
    - method → method
    - description → api_name, remark
    - notes → remark (追加)
    """
    result: List[Dict[str, Any]] = []
    for item in summary:
        url = str(item.get("api_path", ""))
        method = str(item.get("method", "GET")).upper()
        description = str(item.get("description", ""))

        clean = (
            url.strip("/")
            .replace("/", "_")
            .replace("-", "_")
            .replace("{", "")
            .replace("}", "")
            .lower()
        )
        test_id = f"api_{clean}_{method.lower()}" if clean else ""

        name = description or f"{method} {url}"
        remark = description
        notes = str(item.get("notes", ""))
        if notes:
            remark = f"{description} | {notes}" if description else notes

        result.append({
            "test_id": test_id,
            "api_name": name,
            "app_name": "default",
            "method": method,
            "url": url,
            "request_head": {"Content-Type": "application/json"},
            "request_body": {},
            "status_code": 200,
            "assert_dict": {"status_code": 200},
            "remark": remark,
        })
    return result


def _dicts_to_interfaces(items: List[Any]) -> List[InterfaceDef]:
    """Convert a mixed list of dicts/InterfaceDef to unified List[InterfaceDef]."""
    result = []
    for item in items:
        if isinstance(item, InterfaceDef):
            result.append(item)
        elif isinstance(item, dict):
            try:
                result.append(InterfaceDef(
                    test_id=str(item.get("test_id", "")),
                    api_name=str(item.get("api_name", item.get("name", ""))),
                    app_name=str(item.get("app_name", item.get("app", ""))),
                    method=str(item.get("method", "GET")).upper(),
                    url=str(item.get("url", "")),
                    request_head=dict(item.get("request_head", item.get("headers", {})) or {}),
                    request_body=dict(item.get("request_body", item.get("body", item.get("params", {}))) or {}),
                    status_code=int(item.get("status_code", 200)),
                    assert_dict=dict(item.get("assert_dict", item.get("assertion", {})) or {}),
                    assert_rules=list(item.get("assert_rules", []) or []),
                    remark=str(item.get("remark", item.get("note", ""))),
                ))
            except Exception as e:
                logger.warning("Failed to convert dict to InterfaceDef: %s", e)
        else:
            logger.warning("Unexpected interface item type: %s", type(item))
    return result
