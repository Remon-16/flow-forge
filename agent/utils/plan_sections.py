"""计划章节工具 / Plan section utilities — 标题扫描、级别检测、分类。

Extracted from graph/nodes/review.py for reuse by PlanParser and other agents.
提供 `_scan_headings()` 和 `_detect_section_level()` 两个共享函数。
"""

import re
from collections import Counter
from typing import List, Tuple

_HEADING_RE = re.compile(r"(?m)^(#{1,6})[ \t]+\S")

# 区块分类关键词 / Section classification keywords
_GLOBAL_KEYWORDS = [
    "商业理解", "Business Understanding",
    "流程图", "Flowchart", "Mermaid",
]
_API_KEYWORDS = [
    "单接口测试点", "Single Interface Test Points",
    "接口测试", "Interface Test",
]
_BIZ_KEYWORDS = [
    "商业流程测试", "Business Flow Testing",
    "流程测试", "Flow Testing",
]


def scan_headings(content: str) -> List[Tuple[int, int, str]]:
    """扫描所有 Markdown 标题 / Scan all markdown headings.

    Returns [(offset, level, line_text), ...] — 级别由 # 数量决定, 不写死。
    Returns [(offset, level, line_text), ...] — level is dynamic, not hard-coded.
    """
    headings = []
    for m in _HEADING_RE.finditer(content):
        offset = m.start()
        level = len(m.group(1))
        line_end = content.find("\n", offset)
        if line_end == -1:
            line_end = len(content)
        headings.append((offset, level, content[offset:line_end]))
    return headings


def detect_section_level(plan_md: str) -> int:
    """检测文档的主分段标题级别 / Detect primary sectioning heading level.

    规则: 出现次数 > 1 的最浅（# 最少）标题级别。
    Rule: shallowest (fewest #) heading level that appears more than once.
    Returns 2 as fallback when no suitable level found.
    """
    headings = scan_headings(plan_md)
    if not headings:
        return 2
    level_counts = Counter(h[1] for h in headings)
    for level in sorted(level_counts.keys()):
        if level_counts[level] > 1:
            return level
    # 所有级别都只出现一次 → 用最浅级别
    # All levels appear only once → use shallowest
    return min(level_counts.keys())


def classify_section(heading_text: str) -> str:
    """根据标题文本关键词分类区块类型 / Classify section by heading keywords.

    Returns "global", "api", "biz", or "unknown".
    """
    for kw in _GLOBAL_KEYWORDS:
        if kw in heading_text:
            return "global"
    for kw in _API_KEYWORDS:
        if kw in heading_text:
            return "api"
    for kw in _BIZ_KEYWORDS:
        if kw in heading_text:
            return "biz"
    return "unknown"
