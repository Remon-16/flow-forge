"""接口定义保存/重新加载节点。

Interface I/O nodes: save and reload interface definitions as YAML files.
"""

import logging
from pathlib import Path

from graph.state import GraphState
from writers.yaml_writer import YamlWriter

from .helpers import _, _step, _sl, save_pipeline_state, save_snapshot

logger = logging.getLogger(__name__)


def save_interfaces_node(state: GraphState) -> GraphState:
    """在计划审核前保存接口定义为 YAML 文件。

    Save interface definitions as YAML files BEFORE plan review.
    Checks remark fields for ``[URL_MAY_INCORRECT]`` markers.
    """
    state.setdefault("errors", [])

    logger.info(_step("save_interfaces", "pipeline.save_ifaces"))
    if _sl():
        _sl().log_node_start("save_interfaces", "6/9")

    interfaces = state.get("interfaces", [])
    cases_dir = state.get("cases_dir") or state.get("output_dir", "./output")
    memory_dir = state.get("memory_dir", "")
    debug_snapshots = state.get("debug_snapshots", False)

    if not interfaces:
        logger.warning("No interfaces to save")
        return state

    interfaces_dir = Path(cases_dir) / "interfaces"
    interfaces_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    url_issues: list = []
    for iface in interfaces:
        try:
            YamlWriter.write_interface(iface, cases_dir)
            count += 1
            remark = iface.get("remark", "") if isinstance(iface, dict) else getattr(iface, "remark", "")
            if "[URL_MAY_INCORRECT]" in str(remark):
                url_issues.append({
                    "test_id": iface.get("test_id", "?") if isinstance(iface, dict) else getattr(iface, "test_id", "?"),
                    "url": iface.get("url", "?") if isinstance(iface, dict) else getattr(iface, "url", "?"),
                })
        except Exception as e:
            logger.warning("Failed to save interface: %s", e)

    if debug_snapshots and memory_dir:
        save_snapshot(memory_dir, "interfaces.json", interfaces)

    logger.info(_("ifaces.saved", count=count, dir=str(interfaces_dir)))

    if url_issues:
        logger.info(_("ifaces.url_issues"))
        for issue in url_issues:
            logger.info(_("ifaces.url_issue_item", test_id=issue['test_id'], url=issue['url']))

    if _sl():
        _sl().log_event("save_interfaces", count=count, dir=str(interfaces_dir),
                         url_issues=len(url_issues))
        _sl().log_node_end("save_interfaces")

    # Save pipeline state for resume
    if memory_dir:
        save_pipeline_state(memory_dir, "save_interfaces")

    return state


def reload_interfaces_node(state: GraphState) -> GraphState:
    """计划确认后从 YAML 文件重新加载接口定义。

    Reload interface definitions from YAML files after plan confirmation.
    Picks up any manual fixes made during the review phase.
    """
    state.setdefault("errors", [])

    cases_dir = state.get("cases_dir") or state.get("output_dir", "./output")
    interfaces_dir = Path(cases_dir) / "interfaces"

    if not interfaces_dir.is_dir():
        logger.warning("Interfaces directory not found: %s", interfaces_dir)
        return state

    logger.info(_("ifaces.reloading"))
    if _sl():
        _sl().log_node_start("reload_interfaces", "reload")

    reloaded = YamlWriter.read_interfaces(str(cases_dir))
    if not reloaded:
        logger.warning("No interfaces reloaded — keeping existing state")
        if _sl():
            _sl().log_node_end("reload_interfaces")
        return state

    # Quick URL re-check (substring only, no LLM)
    api_raw_text = state.get("api_raw_text", "")
    url_issues = []
    for iface in reloaded:
        url = iface.get("url", "")
        if url and api_raw_text and url not in api_raw_text:
            url_issues.append({"test_id": iface.get("test_id", "?"), "url": url})

    if url_issues:
        logger.info(_("ifaces.url_still_issues", count=len(url_issues)))
        for issue in url_issues:
            logger.info(_("ifaces.url_issue_item", test_id=issue['test_id'], url=issue['url']))

    state["interfaces"] = reloaded
    logger.info(_("ifaces.reloaded", count=len(reloaded)))

    if _sl():
        _sl().log_event("reload_interfaces", count=len(reloaded), url_issues=len(url_issues))
        _sl().log_node_end("reload_interfaces")

    return state
