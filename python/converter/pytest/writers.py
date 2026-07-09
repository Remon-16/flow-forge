"""pytest 测试文件写入器。
   pytest test file writers."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from i18n import _

from .templates import CONFTEST_TEMPLATE, SINGLE_HEADER, BIZ_HEADER
from .generators import generate_single_test, generate_biz_flow_class

logger = logging.getLogger(__name__)


def write_conftest(output_dir: str) -> None:
    """写入 conftest.py — fixtures + 辅助函数 + 处理器实现。
       Write conftest.py — fixtures + helper functions + processor implementations."""
    path = Path(output_dir) / "conftest.py"
    path.write_text(CONFTEST_TEMPLATE, encoding="utf-8")
    logger.info(_("converter.wrote_conftest", path=str(path)))


def write_single_tests(cases: list[dict[str, Any]], output_dir: str) -> int:
    """生成并写入 test_single_cases.py。返回用例数。
       Generate and write test_single_cases.py. Returns case count."""
    if not cases:
        return 0
    parts = [SINGLE_HEADER]
    for i, case in enumerate(cases):
        parts.append(generate_single_test(case, i))
    path = Path(output_dir) / "test_single_cases.py"
    path.write_text("".join(parts), encoding="utf-8")
    logger.info(_("converter.wrote_single_tests", count=len(cases), path=str(path)))
    return len(cases)


def write_biz_flow_tests(flows: list[dict[str, Any]], output_dir: str) -> int:
    """生成并写入 test_biz_flows.py。返回流程数。
       Generate and write test_biz_flows.py. Returns flow count."""
    if not flows:
        return 0
    parts = [BIZ_HEADER]
    for i, flow in enumerate(flows):
        src = generate_biz_flow_class(flow, i)
        if src:
            parts.append(src)
    path = Path(output_dir) / "test_biz_flows.py"
    path.write_text("".join(parts), encoding="utf-8")
    step_count = sum(len(f.get("steps", [])) for f in flows)
    logger.info(_("converter.wrote_biz_flow_tests", count=len(flows), steps=step_count, path=str(path)))
    return len(flows)
