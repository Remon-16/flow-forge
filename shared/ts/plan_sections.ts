// plan_sections.json 的 TypeScript 类型定义与 helper 函数。
// TypeScript type definitions and helper functions for plan_sections.json.
//
// 对应 JSON Schema: shared/schemas/plan_sections.json
// Corresponding JSON Schema: shared/schemas/plan_sections.json

/** 业务理解全局章节 / Business understanding global section */
export interface GlobalSection {
  chunk_id: string         // "business_understanding"
  key: string              // "business_understanding"
  type: 'global'
  name: string             // 人类可读名称 / Human-readable name
  content: string          // 业务理解 markdown 文本 / Business understanding markdown text
}

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
  business_understanding: GlobalSection
  single_api: ApiSection[]
  biz_flows: BizSection[]
}

/** 从 sections 组装 plan.md（含 chunk 边界标记，供 Studio 批注器使用）。
 *  Assemble plan.md from sections (with chunk boundary markers for Studio annotator).
 *  Python 侧对应的 assemble_plan_md() 不含 chunk 标记，仅用于流水线内部组装。
 *  The Python-side assemble_plan_md() omits chunk markers, used only for internal pipeline assembly.
 *  章节标题由 SECTION_HEADINGS 统一管理，LLM 不再生成。
 *  Section headings are managed by SECTION_HEADINGS; LLM no longer generates them. */

import sectionHeadingsData from '../schemas/section_headings.json'

/** 跨语言 section 章节标题 / Cross-language section headings */
export const SECTION_HEADINGS: Record<string, Record<string, string>> = sectionHeadingsData.headings

export function assemblePlanMd(sections: PlanSections, language: string = 'zh-CN'): string {
  const h = SECTION_HEADINGS
  const parts: string[] = []

  // 业务理解 / Business understanding
  const buContent = sections.business_understanding?.content?.trim()
  const buChunkId = sections.business_understanding?.chunk_id || 'business_understanding'
  if (buContent) {
    const heading = h.business_understanding?.[language] || ''
    parts.push(`<!-- chunk:${buChunkId} -->\n\n` + (heading ? heading + '\n\n' : '') + buContent)
  }

  // 单接口测试 / Single API test points
  for (const sec of sections.single_api) {
    if (sec.content?.trim()) {
      const heading = h.single_api?.[language] || ''
      parts.push(`<!-- chunk:${sec.chunk_id} -->\n\n` + (heading ? heading + '\n\n' : '') + sec.content.trim())
    }
  }

  // 业务链路测试 / Business flow testing: 文本在前，流程图在后 / content first, mermaid at end
  let isFirstBiz = true
  for (const sec of sections.biz_flows) {
    const content = sec.content?.trim() || ''
    const mermaid = sec.mermaid?.trim() || ''
    if (!content && !mermaid) continue

    const assembled: string[] = []
    if (isFirstBiz) {
      const heading = h.biz_flows?.[language] || ''
      if (heading) assembled.push(heading)
    }
    isFirstBiz = false
    if (content) assembled.push(content)
    if (mermaid) assembled.push(mermaid)

    parts.push(`<!-- chunk:${sec.chunk_id} -->\n\n` + assembled.join('\n\n'))
  }
  return parts.join('\n\n')
}
