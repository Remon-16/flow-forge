"""文档解析节点 — 读取需求文档和 API 规范。

parse_docs node: reads requirement files and API specification.
"""

import logging
from pathlib import Path
from typing import List

from doc_parser.llm_parser import DocParserAgent
from doc_parser.pdf_parser import PdfParser
from doc_parser.text_extractor import extract_text
from graph.state import GraphState

from .helpers import _settings, _sl, fmt_size, iface_to_dict, save_snapshot

logger = logging.getLogger(__name__)


def parse_docs_node(state: GraphState) -> GraphState:
    """读取需求文件和 API 规范文档。

    Read requirement files + API spec. Three parse modes:
    - raw: extract text, defer analysis to analyze_api_node
    - rule: use built-in/custom rule-based parsers
    - llm: use DocParserAgent (LLM) to pre-extract structured interfaces
    """
    state.setdefault("errors", [])

    print(_step("parse_docs", "pipeline.reading_docs"))

    # --- Requirements ---
    requirement_text_parts: List[str] = []
    for path in state.get("requirement_paths", []):
        size_str = fmt_size(path)
        ext = Path(path).suffix.lower()
        try:
            if ext in (".txt", ".md"):
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                    requirement_text_parts.append(content)
                print(_("parse_docs.read_file", path=path, size=size_str))
                if _sl():
                    _sl().log_file_read(path, len(content))
            elif ext == ".pdf":
                content = PdfParser.parse(path)
                requirement_text_parts.append(content)
                print(_("parse_docs.pdf_parsing", path=path, size=size_str))
                if _sl():
                    _sl().log_file_read(path, len(content))
            else:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                    requirement_text_parts.append(content)
                print(_("parse_docs.read_file", path=path, size=size_str))
                if _sl():
                    _sl().log_file_read(path, len(content))
        except Exception as e:
            msg = f"Failed to read requirement file '{path}': {e}"
            logger.error(msg)
            state["errors"].append(msg)
            print(_("batch.error", msg=msg))

    state["requirement_text"] = "\n\n".join(requirement_text_parts)

    # --- API ---
    api_path = state.get("api_path", "")
    parse_mode = state.get("parse_mode", "raw")
    state["interfaces_from_llm"] = False

    if not api_path:
        state["interfaces"] = []
        state["interface_extraction_method"] = "none"
        return state

    size_str = fmt_size(api_path)
    ext = Path(api_path).suffix.lower()

    print(_("parse_docs.parse_mode", mode=parse_mode))

    if parse_mode == "raw":
        raw_text = extract_text(api_path)
        if not raw_text.strip():
            raise Exception(f"API 文档 '{api_path}' 内容为空，无法解析。")
        state["api_raw_text"] = raw_text
        state["interfaces"] = []
        state["interface_extraction_method"] = "raw"
        print(_("parse_docs.read_api_doc", size=size_str, chars=len(raw_text)))
        print(_("parse_docs.api_identify_next"))

    elif parse_mode == "rule":
        from .analyze_api import _dispatch_rule_parser
        interfaces = _dispatch_rule_parser(api_path, state.get("parser_path", ""))
        if len(interfaces) == 0:
            raise Exception(
                f"规则解析器未从 '{api_path}' 提取到接口。\n"
                f"建议：\n"
                f"  1. 尝试 --parse-mode raw（默认，让 LLM 直接从原文识别接口）\n"
                f"  2. 尝试 --parse-mode llm（用 LLM 预提取结构化接口）\n"
                f"  3. 编写自定义解析器: --parser-path /path/to/parser.py"
            )
        state["interfaces"] = [iface_to_dict(i) for i in interfaces]
        state["interface_extraction_method"] = "rule"
        print(_("parse_docs.rule_done", count=len(interfaces)))

    elif parse_mode == "llm":
        raw_text = extract_text(api_path)
        if not raw_text.strip():
            raise Exception(f"API 文档 '{api_path}' 内容为空，无法解析。")
        print(_("parse_docs.read_api_doc", size=size_str, chars=len(raw_text)))
        print(_("parse_docs.llm_extracting", model=_settings.llm_model))
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
        state["interfaces"] = [iface_to_dict(i) for i in interfaces]
        state["interfaces_from_llm"] = True
        state["api_raw_text"] = raw_text
        state["interface_extraction_method"] = "llm"
        print(_("parse_docs.llm_extracted", count=len(interfaces)))

    else:
        raise Exception(f"未知的解析模式: {parse_mode}。支持的模式: raw (默认), rule, llm")

    if _sl():
        _sl().log_file_read(api_path, Path(api_path).stat().st_size)

    if state.get("debug_snapshots") and state.get("memory_dir"):
        save_snapshot(state["memory_dir"], "extracted_texts.json", {
            "requirement_text": state.get("requirement_text", ""),
            "api_raw_text": state.get("api_raw_text", ""),
            "requirement_files": state.get("requirement_paths", []),
            "api_file": state.get("api_path", ""),
        })

    return state
