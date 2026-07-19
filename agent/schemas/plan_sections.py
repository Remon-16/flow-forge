"""plan_sections.json 的 Python 类型定义与 helper 函数。

Python type definitions and helper functions for plan_sections.json.

对应 JSON Schema: agent/schemas/plan_sections.schema.json
Corresponding JSON Schema: agent/schemas/plan_sections.schema.json
"""

from __future__ import annotations

from typing import List, Literal, TypedDict


# ============================================================================
# TypedDict 定义 / TypedDict definitions
# ============================================================================


class ApiSection(TypedDict):
    """单接口用例 section / Single API test case section."""
    chunk_id: str
    key: str
    type: Literal["api"]
    name: str
    section: Literal["single_api"]
    content: str       # markdown 文本描述 / Markdown text description
    api_ids: List[str]         # 该 group 包含的接口 test_id 列表。fix 时查 InterfaceDef 用 / Interface test_ids in this group; used in fix to look up InterfaceDef
    test_focus: str            # 该 group 的测试重点描述。fix 时作为 LLM prompt 补充 / Testing focus description; used as LLM prompt context during fix


class BizSection(TypedDict):
    """业务链路用例 section / Business flow test case section."""
    chunk_id: str
    key: str
    type: Literal["biz"]
    name: str
    section: Literal["biz_flows"]
    content: str       # markdown 文本描述，不含 Mermaid / Markdown text, no Mermaid
    mermaid: str       # Mermaid 流程图 / Mermaid flowchart diagram
    involved_apis: List[str]   # 该业务流涉及的接口 test_id 列表。fix/重画 Mermaid 时查 InterfaceDef 用 / Interface test_ids involved; used in fix/mermaid regen
    description: str           # 该业务流的文字描述。fix/重画 Mermaid 时作为 LLM prompt 上下文 / Flow description; used as LLM prompt context during fix/mermaid regen


class PlanSections(TypedDict):
    """plan_sections.json 的顶层结构 / Top-level structure of plan_sections.json."""
    business_understanding: str
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


def find_section_by_key(sections: PlanSections, key: str) -> ApiSection | BizSection | None:
    """在 single_api 和 biz_flows 数组中按 key 查找 section。

    Find a section by key across single_api and biz_flows arrays.
    """
    for sec in sections.get("single_api", []):
        if sec.get("key") == key:
            return sec
    for sec in sections.get("biz_flows", []):
        if sec.get("key") == key:
            return sec
    return None


def delete_section_by_key(sections: PlanSections, key: str) -> bool:
    """从 single_api 或 biz_flows 中删除指定 key 的 section。

    Delete the section with the given key from single_api or biz_flows.
    Returns True if deleted, False if not found.
    """
    for arr_name in ("single_api", "biz_flows"):
        arr = sections.get(arr_name, [])
        for i, sec in enumerate(arr):
            if sec.get("key") == key:
                arr.pop(i)
                return True
    return False


def assemble_plan_md(sections: PlanSections) -> str:
    """从 PlanSections 组装 plan.md 字符串。

    Assemble a plan.md string from PlanSections.
    对 biz_flows 的每个 section，在 content 前 prepend mermaid。
    For each biz_flows section, prepend mermaid before content.
    """
    parts: List[str] = []

    bu = sections.get("business_understanding", "")
    if bu.strip():
        parts.append(bu.strip())

    for sec in sections.get("single_api", []):
        content = sec.get("content", "")
        if content.strip():
            parts.append(content.strip())

    for sec in sections.get("biz_flows", []):
        content = sec.get("content", "")
        mermaid = sec.get("mermaid", "")
        combined_parts = []
        if mermaid.strip():
            combined_parts.append(mermaid.strip())
        if content.strip():
            combined_parts.append(content.strip())
        if combined_parts:
            parts.append("\n\n".join(combined_parts))

    return "\n\n".join(parts)
