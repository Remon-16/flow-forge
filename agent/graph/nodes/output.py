"""输出写入节点 — 将最终结果写入 YAML/Excel。

Output nodes: write final results as YAML and optionally Excel.
"""

import logging
from pathlib import Path

from agents.excel_writer import ExcelWriter
from graph.state import GraphState

from .helpers import _, _step, _sl, dicts_to_interfaces

logger = logging.getLogger(__name__)


def write_output_node(state: GraphState) -> GraphState:
    """写入最终输出：YAML 已保存；可选转换为 Excel。

    Write final output: YAML already saved; optionally convert to Excel.
    """
    state.setdefault("errors", [])

    output_format = state.get("output_format", "both")
    output_dir = state.get("output_dir", "./output")
    cases_dir = state.get("cases_dir") or state.get("output_dir", "./output")
    output_path = state.get("output_path", "test_cases.xlsx")
    failures = state.get("validation_failures", [])

    print(_step("write_output", "pipeline.write_output"))
    if _sl():
        _sl().log_node_start("write_output", "9/9")

    if output_format in ("excel", "both"):
        try:
            ExcelWriter.yaml_to_excel(cases_dir, output_path)
            print(_("output.excel_written", path=output_path))
            if _sl():
                excel_copy = _sl().save_excel(output_path)
                if excel_copy:
                    print(_("output.excel_backed_up", path=excel_copy))
        except Exception as e:
            msg = f"Failed to write Excel: {e}"
            logger.error(msg)
            state["errors"].append(msg)
            print(_("batch.error", msg=msg))

    if output_format in ("yaml", "both"):
        print(_("output.yaml_saved", dir=cases_dir, iface_count=_count_yaml(cases_dir, "interfaces"), single_count=_count_yaml(cases_dir, "single_cases"), biz_count=_count_yaml(cases_dir, "biz_flows")))

    if failures:
        print(_("output.validation_failed", count=len(failures), dir=cases_dir))

    if _sl():
        _sl().log_node_end("write_output")

    return state


def write_excel_node(state: GraphState) -> GraphState:
    """写入最终 Excel 文件（旧版单次模式）。

    Write the final test case Excel file (legacy single-shot mode).
    """
    state.setdefault("errors", [])

    output = state.get("output_path", "test_cases.xlsx")
    interfaces_raw = state.get("interfaces", [])
    single = state.get("single_cases", [])
    biz = state.get("biz_flows", [])

    print(_("output.excel_writing"))
    if _sl():
        _sl().log_node_start("write_excel", "8/8")

    interfaces = dicts_to_interfaces(interfaces_raw)

    try:
        ExcelWriter.write(interfaces, single, biz, output)
        print(_("output.excel_written_to", path=output))
        if _sl():
            excel_copy = _sl().save_excel(output)
            if excel_copy:
                print(_("output.excel_backed_up", path=excel_copy))
        sheet_count = 2 + len(biz)
        print(_("output.sheet_count", sheets=sheet_count, single=len(single), biz=len(biz)))
    except Exception as e:
        msg = f"Failed to write Excel: {e}"
        logger.error(msg)
        state["errors"].append(msg)
        print(_("batch.error", msg=msg))

    if _sl():
        _sl().log_node_end("write_excel")

    return state


def _count_yaml(output_dir: str, subdir: str) -> int:
    p = Path(output_dir) / subdir
    return len(list(p.glob("*.yaml"))) if p.is_dir() else 0
