// plan_sections.json 的 TypeScript 类型定义与 helper 函数。
// TypeScript type definitions and helper functions for plan_sections.json.
//
// 对应 JSON Schema: shared/schemas/plan_sections.json
// Corresponding JSON Schema: shared/schemas/plan_sections.json

/** 单接口用例 section / Single API test case section */
export interface ApiSection {
  chunk_id: string
  key: string
  type: 'api'
  name: string
  section: 'single_api'
  content: string       // markdown，不含 Mermaid / markdown, no Mermaid
  api_ids?: string[]    // 该 group 的接口 test_id 列表。fix 时查 InterfaceDef 用 / Interface test_ids; used in fix to look up InterfaceDef
  test_focus?: string   // 该 group 的测试重点描述。fix 时 LLM prompt 补充 / Testing focus; used as LLM prompt context during fix
}

/** 业务链路用例 section / Business flow test case section */
export interface BizSection {
  chunk_id: string
  key: string
  type: 'biz'
  name: string
  section: 'biz_flows'
  content: string            // markdown，不含 Mermaid / markdown, no Mermaid
  mermaid: string            // Mermaid 流程图 / Mermaid flowchart
  involved_apis?: string[]   // 该流涉及的接口 test_id 列表。fix/重画 Mermaid 时查 InterfaceDef / Interface test_ids; used in fix/mermaid regen
  description?: string       // 该流的文字描述。fix/重画 Mermaid 时 LLM prompt 上下文 / Flow description; used as LLM prompt context
}

/** plan_sections.json 顶层结构 / Top-level structure */
export interface PlanSections {
  business_understanding: string
  single_api: ApiSection[]
  biz_flows: BizSection[]
}

/** 从 sections 组装 plan.md（含 chunk 边界标记，供 Studio 批注器使用）。
 *  Assemble plan.md from sections (with chunk boundary markers for Studio annotator).
 *  Python 侧对应的 assemble_plan_md() 不含 chunk 标记，仅用于流水线内部组装。
 *  The Python-side assemble_plan_md() omits chunk markers, used only for internal pipeline assembly. */
export function assemblePlanMd(sections: PlanSections): string {
  const parts: string[] = []
  if (sections.business_understanding?.trim()) {
    parts.push('<!-- chunk:__global__ -->\n\n' + sections.business_understanding.trim())
  }
  for (const sec of sections.single_api) {
    if (sec.content?.trim()) {
      parts.push(`<!-- chunk:${sec.chunk_id} -->\n\n` + sec.content.trim())
    }
  }
  for (const sec of sections.biz_flows) {
    const combined: string[] = []
    if (sec.mermaid?.trim()) combined.push(sec.mermaid.trim())
    if (sec.content?.trim()) combined.push(sec.content.trim())
    if (combined.length) {
      parts.push(`<!-- chunk:${sec.chunk_id} -->\n\n` + combined.join('\n\n'))
    }
  }
  return parts.join('\n\n')
}
