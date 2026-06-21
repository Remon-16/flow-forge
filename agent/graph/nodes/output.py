"""输出写入节点 — 将最终结果写入 YAML/Excel。

Output nodes: write final results as YAML and optionally Excel.
"""

import logging
from pathlib import Path

from agents.excel_writer import ExcelWriter
from graph.state import GraphState

from .helpers import _sl, dicts_to_interfaces

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

    print(f"\n[9/9] 写入输出...")
    if _sl():
        _sl().log_node_start("write_output", "9/9")

    if output_format in ("excel", "both"):
        try:
            ExcelWriter.yaml_to_excel(cases_dir, output_path)
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
        print(f"  → YAML 用例已保存到 {cases_dir}")
        print(f"     interfaces/: {_count_yaml(cases_dir, 'interfaces')} 个")
        print(f"     single_cases/: {_count_yaml(cases_dir, 'single_cases')} 个")
        print(f"     biz_flows/: {_count_yaml(cases_dir, 'biz_flows')} 个")

    if failures:
        print(f"  → 校验失败: {len(failures)} 个 (详见 {cases_dir}/failures.yaml)")

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

    print(f"\n[8/8] 写入 Excel...")
    if _sl():
        _sl().log_node_start("write_excel", "8/8")

    interfaces = dicts_to_interfaces(interfaces_raw)

    try:
        ExcelWriter.write(interfaces, single, biz, output)
        print(f"  → 写入 {output}")
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


def _count_yaml(output_dir: str, subdir: str) -> int:
    p = Path(output_dir) / subdir
    return len(list(p.glob("*.yaml"))) if p.is_dir() else 0
