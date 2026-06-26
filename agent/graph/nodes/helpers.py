"""共享辅助函数和模块级依赖注入。

Shared helpers and module-level dependency injection for all nodes.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from config.settings import Settings
from knowledge.search import KnowledgeSearch
from models.schema import InterfaceDef
from prompts.plan_generation import (
    REFERENCE_DIR_EMPTY,
    REFERENCE_DIR_GUIDANCE,
    REFERENCE_DIR_UNREADABLE,
    REF_SECTION_EXISTING_BIZ_FLOWS,
    REF_SECTION_EXISTING_INTERFACES,
    REF_SECTION_EXISTING_PLAN,
    REF_SECTION_EXISTING_SINGLE_CASES,
)
from writers.yaml_writer import YamlWriter

logger = logging.getLogger(__name__)

# 模块级单例 — 由 build_workflow 注入
# Module-level singletons — injected by build_workflow
_settings: Settings = None
_knowledge: Optional[KnowledgeSearch] = None
_session_logger = None


def configure(
    settings: Settings,
    knowledge: Optional[KnowledgeSearch],
    session_logger=None,
):
    """注入模块级依赖。

    Wire module-level dependencies before building the graph.
    """
    global _settings, _knowledge, _session_logger
    _settings = settings
    _knowledge = knowledge
    _session_logger = session_logger

    from tools.builtin import set_knowledge_instance
    set_knowledge_instance(knowledge)

    from agents.base import BaseAgent
    BaseAgent._default_rate_limit_delay = settings.llm_rate_limit_delay
    BaseAgent._default_retry_base_delay = settings.llm_retry_base_delay
    BaseAgent._default_max_concurrency = settings.llm_max_concurrency
    BaseAgent._default_request_timeout = settings.llm_request_timeout


def _sl():
    """获取会话日志记录器（可能为 None）。

    Shorthand to get the session logger (may be None).
    """
    return _session_logger


def save_snapshot(memory_dir: str, filename: str, data: Any) -> None:
    """保存中间流水线状态为 JSON 快照。

    Save intermediate pipeline state as a JSON snapshot.
    """
    if not memory_dir:
        return
    try:
        snapshots_dir = Path(memory_dir) / "snapshots"
        snapshots_dir.mkdir(parents=True, exist_ok=True)
        path = snapshots_dir / filename
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning("Failed to save snapshot %s: %s", filename, e)


def save_pipeline_artifact(memory_dir: str, filename: str, data: Any) -> None:
    """保存流水线中间结果到 memory/ 目录（可靠工件，供 resume 使用）。

    Save pipeline intermediate result as a reliable artifact for resume.
    Unlike snapshots, these are always saved regardless of debug_snapshots flag.
    """
    if not memory_dir:
        return
    try:
        path = Path(memory_dir) / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning("Failed to save pipeline artifact %s: %s", filename, e)


def save_pipeline_state(memory_dir: str, stage: str) -> None:
    """更新流水线进度标记文件。

    Update pipeline progress marker file for resume routing.
    """
    if not memory_dir:
        return
    try:
        path = Path(memory_dir) / "pipeline_state.json"
        state: Dict[str, Any] = {"completed_stage": stage, "stages": []}
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                state = json.load(f)
        if stage not in state.get("stages", []):
            state.setdefault("stages", []).append(stage)
        state["completed_stage"] = stage
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning("Failed to save pipeline state: %s", e)


def fmt_size(path: str) -> str:
    """格式化文件大小以供显示。

    Format file size for display.
    """
    try:
        size = Path(path).stat().st_size
        if size >= 1024:
            return f"{size / 1024:.1f} KB"
        return f"{size} B"
    except OSError:
        return "? B"


def summarize_reference_dir(reference_dir: str) -> str:
    """扫描参考目录获取已有测试资产摘要。

    Scan reference directory for existing test assets and return a summary
    for the plan generation prompt. Returns "(none)" if empty.
    """
    if not reference_dir:
        return REFERENCE_DIR_EMPTY

    ref_path = Path(reference_dir)
    parts = []

    ref_cases = ref_path / "cases" if (ref_path / "cases").is_dir() else ref_path
    ref_memory = ref_path / "memory" if (ref_path / "memory").is_dir() else ref_path

    # 已有测试计划 / Existing plan
    plan_path = ref_memory / "plan.md"
    if not plan_path.exists():
        plan_path = ref_path / "plan.md"
    if plan_path.exists():
        try:
            plan_text = plan_path.read_text(encoding="utf-8")
            parts.append(f"{REF_SECTION_EXISTING_PLAN}{plan_text[:5000]}")
        except Exception:
            pass

    # 已有接口 / Existing interfaces
    try:
        ifaces = YamlWriter.read_interfaces(ref_cases)
        if ifaces:
            lines = [
                f"- {i.get('test_id', '?')}: {i.get('method', 'GET')} {i.get('url', '')}"
                for i in ifaces
            ]
            parts.append(REF_SECTION_EXISTING_INTERFACES.format(count=len(ifaces)) + "\n".join(lines))
    except Exception:
        pass

    # 已有单接口用例 / Existing single cases
    try:
        cases = YamlWriter.read_single_cases(ref_cases)
        if cases:
            ids = [str(c.get("test_id", "?")) for c in cases]
            parts.append(
                REF_SECTION_EXISTING_SINGLE_CASES.format(
                    count=len(cases), ids=', '.join(ids[:50])
                )
            )
    except Exception:
        pass

    # 已有业务链路用例 / Existing biz flows
    try:
        flows = YamlWriter.read_biz_flows(ref_cases)
        if flows:
            names = [str(f.get("sheet_name", "?")) for f in flows]
            parts.append(
                REF_SECTION_EXISTING_BIZ_FLOWS.format(
                    count=len(flows), names=', '.join(names[:20])
                )
            )
    except Exception:
        pass

    if not parts:
        return REFERENCE_DIR_UNREADABLE

    parts.append(REFERENCE_DIR_GUIDANCE)
    return "\n\n".join(parts)


def iface_to_dict(i: InterfaceDef) -> Dict[str, Any]:
    """InterfaceDef → 字典。Convert InterfaceDef to dict."""
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


def summary_to_interfaces(summary: List[Dict]) -> List[Dict[str, Any]]:
    """从 ApiAnalyzer 摘要重建接口定义字典。

    Convert ApiAnalyzer summary dicts to InterfaceDef-like dicts.
    """
    result: List[Dict[str, Any]] = []
    for item in summary:
        url = str(item.get("api_path", ""))
        method = str(item.get("method", "GET")).upper()
        description = str(item.get("description", ""))

        clean = (
            url.strip("/").replace("/", "_").replace("-", "_")
            .replace("{", "").replace("}", "").lower()
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


def dicts_to_interfaces(items: List[Any]) -> List[InterfaceDef]:
    """混合列表（dict/InterfaceDef）→ 统一的 List[InterfaceDef]。

    Convert mixed list of dicts/InterfaceDef to unified List[InterfaceDef].
    """
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
