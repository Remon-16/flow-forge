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
 *  The Python-side assemble_plan_md() omits chunk markers, used only for internal pipeline assembly. */

/** biz section 内容中插入 mermaid 到标题之后 / Insert mermaid after headings in biz content.
 *  将 mermaid 放在 ##/### 标题行之后而非 content 最前面，
 *  避免流程图在视觉上出现在标题上方。
 *  Places mermaid after heading lines, not before them,
 *  so the diagram renders below the section heading visually. */
function insertMermaidAfterHeading(content: string, mermaid: string): string {
  const lines = content.split('\n')
  // 找到标题块结束位置（连续的 # 开头行）/ Find where heading block ends (consecutive # lines)
  let headingEnd = 0
  let foundHeading = false
  for (let i = 0; i < lines.length; i++) {
    const trimmed = lines[i].trim()
    if (/^#{1,3}\s/.test(trimmed)) {
      foundHeading = true
      headingEnd = i + 1
      // 连续标题行一起处理 / Handle consecutive heading lines together
      if (i + 1 < lines.length && /^#{1,3}\s/.test(lines[i + 1].trim())) {
        headingEnd = i + 2
      }
      break
    }
    headingEnd = i + 1
  }
  if (!foundHeading) {
    // 没有标题行，mermaid 放在最前面 / No heading found, put mermaid first
    return mermaid + '\n\n' + content
  }
  const headingPart = lines.slice(0, headingEnd).join('\n')
  const restPart = lines.slice(headingEnd).join('\n').trim()
  return headingPart + '\n\n' + mermaid + (restPart ? '\n\n' + restPart : '')
}

export function assemblePlanMd(sections: PlanSections): string {
  const parts: string[] = []
  const buContent = sections.business_understanding?.content?.trim()
  const buChunkId = sections.business_understanding?.chunk_id || 'business_understanding'
  if (buContent) {
    parts.push(`<!-- chunk:${buChunkId} -->\n\n` + buContent)
  }
  for (const sec of sections.single_api) {
    if (sec.content?.trim()) {
      parts.push(`<!-- chunk:${sec.chunk_id} -->\n\n` + sec.content.trim())
    }
  }
  // Biz flows: mermaid 插入标题之后 + 去重 ## 3. 标题 / Insert mermaid after heading + dedup ## 3. headings
  let isFirstBiz = true
  for (const sec of sections.biz_flows) {
    let content = sec.content?.trim() || ''
    const mermaid = sec.mermaid?.trim() || ''
    if (!content && !mermaid) continue

    // 标题去重：仅第一个 biz section 保留 "## 3. 业务流程测试"
    // Heading dedup: only first biz section keeps "## 3. Business Process Testing"
    if (!isFirstBiz) {
      content = content.replace(/^##\s+3\.\s+[^\n]*\n+/m, '')
    }
    isFirstBiz = false

    // Mermaid 插入到标题行之后，而非 content 最前面
    // Insert mermaid after heading lines, not before content
    let assembled: string
    if (mermaid) {
      assembled = insertMermaidAfterHeading(content, mermaid)
    } else {
      assembled = content
    }

    parts.push(`<!-- chunk:${sec.chunk_id} -->\n\n` + assembled.trim())
  }
  return parts.join('\n\n')
}
