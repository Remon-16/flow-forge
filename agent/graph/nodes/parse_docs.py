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

from . import helpers as _h
from .helpers import _, _step, _sl, fmt_size, iface_to_dict, save_pipeline_artifact, save_pipeline_state, save_snapshot

logger = logging.getLogger(__name__)


def parse_docs_node(state: GraphState) -> GraphState:
    """读取需求文件和 API 规范文档。

    Read requirement files + API spec. Three parse modes:
    - raw: extract text, defer analysis to analyze_api_node
    - rule: use built-in/custom rule-based parsers
    - llm: use DocParserAgent (LLM) to pre-extract structured interfaces
    """
    state.setdefault("errors", [])

    logger.info(_step("parse_docs", "pipeline.reading_docs"))

    # --- Requirements（按文件独立存储 / per-file storage）---
    requirement_texts: List[str] = []
    for path in state.get("requirement_paths", []):
        size_str = fmt_size(path)
        ext = Path(path).suffix.lower()
        try:
            if ext in (".txt", ".md"):
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                    requirement_texts.append(content)
                logger.info(_("parse_docs.read_file", path=path, size=size_str))
                if _sl():
                    _sl().log_file_read(path, len(content))
            elif ext == ".pdf":
                content = PdfParser.parse(path)
                requirement_texts.append(content)
                logger.info(_("parse_docs.pdf_parsing", path=path, size=size_str))
                if _sl():
                    _sl().log_file_read(path, len(content))
            else:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                    requirement_texts.append(content)
                logger.info(_("parse_docs.read_file", path=path, size=size_str))
                if _sl():
                    _sl().log_file_read(path, len(content))
        except Exception as e:
            msg = f"Failed to read requirement file '{path}': {e}"
            logger.error(msg)
            state["errors"].append(msg)
            logger.info(_("batch.error", msg=msg))

    state["requirement_texts"] = requirement_texts

    # --- API（多文档独立解析 / multi-doc independent parsing）---
    api_paths = state.get("api_paths", [])
    parse_mode = state.get("parse_mode", "raw")

    if not api_paths:
        state["interfaces"] = []
        state["interface_extraction_method"] = "none"
        state["api_raw_text"] = ""
        state["api_raw_texts"] = []
        return state

    logger.info(_("parse_docs.parse_mode", mode=parse_mode))

    all_interfaces: List[dict] = []
    all_raw_texts: List[str] = []
    seen_keys: set = set()  # (api_path, method) 去重 / dedup by (url, method)
    aggregated_method = parse_mode

    for api_path in api_paths:
        size_str = fmt_size(api_path)
        ext = Path(api_path).suffix.lower()

        if parse_mode == "raw":
            raw_text = extract_text(api_path)
            if not raw_text.strip():
                logger.warning("API document '%s' is empty, skipped.", api_path)
                continue
            if len(raw_text.strip()) < 50:
                logger.info(_("parse_docs.short_text_warning", chars=len(raw_text.strip())))
                logger.warning("API document '%s' contains very little text (%d chars). "
                               "Image-based content will NOT be processed.", api_path, len(raw_text))
            all_raw_texts.append(raw_text)
            logger.info(_("parse_docs.read_api_doc", size=size_str, chars=len(raw_text)))

        elif parse_mode == "rule":
            from .analyze_api import _dispatch_rule_parser
            interfaces = _dispatch_rule_parser(api_path, state.get("parser_path", ""))
            for iface in interfaces:
                d = iface_to_dict(iface)
                key = (d.get("api_path", ""), d.get("method", ""))
                if key not in seen_keys:
                    seen_keys.add(key)
                    all_interfaces.append(d)
            logger.info(_("parse_docs.rule_done", count=len(interfaces)))

        elif parse_mode == "llm":
            raw_text = extract_text(api_path)
            if not raw_text.strip():
                logger.warning("API document '%s' is empty, skipped.", api_path)
                continue
            if len(raw_text.strip()) < 50:
                logger.info(_("parse_docs.short_text_warning", chars=len(raw_text.strip())))
                logger.warning("API document '%s' contains very little text (%d chars). "
                               "Image-based content will NOT be processed.", api_path, len(raw_text))
            all_raw_texts.append(raw_text)
            logger.info(_("parse_docs.read_api_doc", size=size_str, chars=len(raw_text)))
            logger.info(_("parse_docs.llm_extracting", model=_h._settings.llm_model))
            if _sl():
                _sl().log_event("llm_call", agent="DocParserAgent", model=_h._settings.llm_model,
                                text_length=len(raw_text))
            parser_doc = DocParserAgent(_h._settings)
            interfaces = parser_doc.parse(
                raw_text=raw_text,
                file_name=Path(api_path).name,
                file_type_hint=ext,
            )
            for iface in interfaces:
                d = iface_to_dict(iface)
                key = (d.get("api_path", ""), d.get("method", ""))
                if key not in seen_keys:
                    seen_keys.add(key)
                    all_interfaces.append(d)
            aggregated_method = "llm"
            logger.info(_("parse_docs.llm_extracted", count=len(interfaces)))

        else:
            raise Exception(f"Unknown parse mode: {parse_mode}. Supported modes: raw (default), rule, llm")

        if _sl():
            _sl().log_file_read(api_path, Path(api_path).stat().st_size)

    # 合并结果 / Merge results
    if parse_mode == "raw":
        state["api_raw_text"] = "\n\n---\n\n".join(all_raw_texts)
        state["api_raw_texts"] = [{"path": p, "text": t} for p, t in zip(api_paths, all_raw_texts)]
        state["interfaces"] = all_interfaces  # raw 模式下留空，交给后续 analyze_api_node / empty for raw, deferred to analyze_api_node
        state["interface_extraction_method"] = "raw"
        logger.info(_("parse_docs.api_identify_next"))
    else:
        state["api_raw_text"] = "\n\n---\n\n".join(all_raw_texts) if all_raw_texts else ""
        state["api_raw_texts"] = [{"path": p, "text": t} for p, t in zip(api_paths, all_raw_texts)] if all_raw_texts else []
        state["interfaces"] = all_interfaces
        # 至少有一个文件成功用 LLM 解析则标记为 llm / Mark as llm if at least one file used it
        state["interface_extraction_method"] = aggregated_method
        logger.info(_("parse_docs.llm_extracted", count=len(all_interfaces)))

    if state.get("debug_snapshots") and state.get("memory_dir"):
        save_snapshot(state["memory_dir"], "extracted_texts.json", {
            "requirement_texts": requirement_texts,
            "api_raw_text": state.get("api_raw_text", ""),
            "api_raw_texts": state.get("api_raw_texts", []),
            "requirement_files": state.get("requirement_paths", []),
            "api_files": api_paths,
        })

    # Save pipeline artifact for resume
    memory_dir = state.get("memory_dir", "")
    if memory_dir:
        save_pipeline_artifact(memory_dir, "parsed_docs.json", {
            "requirement_texts": requirement_texts,
            "api_raw_text": state.get("api_raw_text", ""),
            "api_raw_texts": state.get("api_raw_texts", []),
            "interfaces": state.get("interfaces", []),
            "parse_mode": state.get("parse_mode", ""),
            "interface_extraction_method": state.get("interface_extraction_method", ""),
        })
        save_pipeline_state(memory_dir, "parse_docs")

    return state
