"""plan_sections.json 的 Python 类型定义与 helper 函数。

Python type definitions and helper functions for plan_sections.json.

对应 JSON Schema: shared/schemas/plan_sections.json
Corresponding JSON Schema: shared/schemas/plan_sections.json
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Literal, NotRequired, TypedDict

# ============================================================================
# Section 章节标题（跨语言 JSON 共享）/ Section headings (cross-language JSON shared)
# ============================================================================

_schema_dir = Path(__file__).resolve().parent.parent.parent / "schemas"
with open(_schema_dir / "section_headings.json", encoding="utf-8") as _f:
    SECTION_HEADINGS: Dict[str, Dict[str, str]] = json.load(_f)["headings"]

# ============================================================================
# TypedDict 定义 / TypedDict definitions
# ============================================================================


class GlobalSection(TypedDict):
    """业务理解全局章节 / Business understanding global section."""
    chunk_id: str                       # "business_understanding"
    key: str                            # "business_understanding"
    type: Literal["global"]
    name: str                           # 人类可读名称 / Human-readable name
    content: str                        # 业务理解 markdown 文本 / Business understanding markdown text


class ApiSection(TypedDict):
    """单接口用例 section / Single API test case section."""
    chunk_id: str
    key: str
    type: Literal["api"]
    name: str
    section: Literal["single_api"]
    content: str               # markdown 文本描述 / Markdown text description
    api_ids: NotRequired[List[str]]    # 该 group 包含的接口 test_id 列表。fix 时查 InterfaceDef 用 / Interface test_ids in this group; used in fix to look up InterfaceDef
    test_focus: NotRequired[str]       # 该 group 的测试重点描述。fix 时作为 LLM prompt 补充 / Testing focus description; used as LLM prompt context during fix


class BizSection(TypedDict):
    """业务链路用例 section / Business flow test case section."""
    chunk_id: str
    key: str
    type: Literal["biz"]
    name: str
    section: Literal["biz_flows"]
    content: str               # markdown 文本描述，不含 Mermaid / Markdown text, no Mermaid
    mermaid: str               # Mermaid 流程图 / Mermaid flowchart diagram
    involved_apis: NotRequired[List[str]]  # 该业务流涉及的接口 test_id 列表。fix/重画 Mermaid 时查 InterfaceDef 用 / Interface test_ids involved; used in fix/mermaid regen
    description: NotRequired[str]          # 该业务流的文字描述。fix/重画 Mermaid 时作为 LLM prompt 上下文 / Flow description; used as LLM prompt context during fix/mermaid regen


class PlanSections(TypedDict):
    """plan_sections.json 的顶层结构 / Top-level structure of plan_sections.json."""
    business_understanding: GlobalSection  # 业务理解全局章节 / Business understanding global section
    single_api: List[ApiSection]
    biz_flows: List[BizSection]


# ============================================================================
# Helper 函数 / Helper functions
# ============================================================================


def make_api_section(chunk_id: str, name: str, content: str) -> ApiSection:
    """创建单接口用例 section / Create a single API test case section."""
    return ApiSection(
        chunk_id=chunk_id,
        key=chunk_id,
        type="api",
        name=name,
        section="single_api",
        content=content,
    )


def make_biz_section(chunk_id: str, name: str, content: str, mermaid: str) -> BizSection:
    """创建业务链路用例 section / Create a business flow test case section."""
    return BizSection(
        chunk_id=chunk_id,
        key=chunk_id,
        type="biz",
        name=name,
        section="biz_flows",
        content=content,
        mermaid=mermaid,
    )


def find_section_by_key(sections: PlanSections, key: str) -> ApiSection | BizSection | GlobalSection | None:
    """在所有 section 中按 key 查找，包括 business_understanding。

    Find a section by key across all sections including business_understanding.
    """
    bu = sections.get("business_understanding")
    if isinstance(bu, dict) and bu.get("key") == key:
        return bu
    for sec in sections.get("single_api", []):
        if sec.get("key") == key:
            return sec
    for sec in sections.get("biz_flows", []):
        if sec.get("key") == key:
            return sec
    return None


def delete_section_by_key(sections: PlanSections, key: str) -> bool:
    """从 sections 中删除指定 key 的 section，包括 business_understanding。

    Delete the section with the given key from any section, including business_understanding.
    Returns True if deleted, False if not found.
    """
    bu = sections.get("business_understanding")
    if isinstance(bu, dict) and bu.get("key") == key:
        sections["business_understanding"] = {}  # 清空但不删除字段 / clear but keep field
        return True
    for arr_name in ("single_api", "biz_flows"):
        arr = sections.get(arr_name, [])
        for i, sec in enumerate(arr):
            if sec.get("key") == key:
                arr.pop(i)
                return True
    return False


def assemble_plan_md(sections: PlanSections, language: str = "zh-CN") -> str:
    """从 PlanSections 组装 plan.md 字符串。

    Assemble a plan.md string from PlanSections.
    章节标题由 SECTION_HEADINGS 统一管理，LLM 不再生成。
    Section headings are managed by SECTION_HEADINGS; LLM no longer generates them.
    """
    h = SECTION_HEADINGS  # 当前语言的标题 / headings for the current language

    parts: List[str] = []

    # 业务理解 / Business understanding
    bu = sections.get("business_understanding", "")
    if isinstance(bu, dict):
        bu_text = bu.get("content", "")
    else:
        bu_text = bu  # 兼容旧格式 / backward compat with old str format
    if bu_text.strip():
        heading = h.get("business_understanding", {}).get(language, "")
        if heading:
            parts.append(heading + "\n\n" + bu_text.strip())
        else:
            parts.append(bu_text.strip())

    # 单接口测试 / Single API test points
    for sec in sections.get("single_api", []):
        content = sec.get("content", "")
        if content and content.strip():
            heading = h.get("single_api", {}).get(language, "")
            if heading:
                parts.append(heading + "\n\n" + content.strip())
            else:
                parts.append(content.strip())

    # 业务链路测试 / Business flow testing
    is_first_biz = True
    for sec in sections.get("biz_flows", []):
        content = sec.get("content", "")
        mermaid = sec.get("mermaid", "")
        if not content.strip() and not mermaid.strip():
            continue

        content = content.strip()
        mermaid = mermaid.strip()

        assembled_parts: List[str] = []
        if is_first_biz:
            heading = h.get("biz_flows", {}).get(language, "")
            if heading:
                assembled_parts.append(heading)
        is_first_biz = False

        if content:
            assembled_parts.append(content)
        if mermaid:
            assembled_parts.append(mermaid)

        if assembled_parts:
            parts.append("\n\n".join(assembled_parts))

    return "\n\n".join(parts)
