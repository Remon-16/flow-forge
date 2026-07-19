// Agent Runner — TypeScript type definitions.
// 智能体执行器 — TypeScript 类型定义。

// ============================================================================
// Task & Session / 任务与会话
// ============================================================================

export type TaskStatus =
  | 'pending'
  | 'running'
  | 'question'
  | 'completed'
  | 'error'

export interface AgentTask {
  id: string
  name: string
  outputDir: string
  status: TaskStatus
  createdAt: number          // Unix timestamp ms
  updatedAt: number
  // Form data (saved at creation time)
  requirementPaths: string
  apiPaths: string
  autoMode: boolean
  userGuidance: string
  caseType: 'single' | 'biz' | 'both'
  // Runtime state
  pendingPrompt?: PromptData | PlanReviewData
  logLines: LogEntry[]
  summary?: CompletionSummary
  error?: string
}

export interface LogEntry {
  ts: string
  level: 'info' | 'warn' | 'error'
  message: string
}

// ============================================================================
// Basic Environment Settings / 基本环境设置
// ============================================================================

export interface AgentConfig {
  agentRootDir: string
  pythonExePath: string        // optional, 手动覆盖 / manual override
  venvPath: string             // optional, envType='venv' 时使用 / used when envType='venv'
  executorRootDir: string      // 执行器根目录 / Executor root directory
  saveToEnvFile: boolean       // 是否将 CLI 参数同步到 env 文件 / Whether to sync CLI params to env file
  // ---- 环境类型 / Environment type ----
  envType: 'system' | 'venv' | 'conda'   // Python 环境类型 / Python environment type
  condaEnvName: string                    // Conda 环境名称（envType='conda' 时使用）/ Conda env name
}

// ============================================================================
// Protocol Events (from agent stdout) / 协议事件（从 agent stdout 接收）
// ============================================================================

export interface AgentLogEvent {
  type: 'log'
  level: string
  message: string
  ts: string
}

export interface AgentProgressEvent {
  type: 'progress'
  stage: string
  step?: string
  detail?: string
  ts: string
}

export interface PromptData {
  id: string
  kind: 'api_clarification'
  message: string
  data: {
    uncertainties: UncertaintyItem[]
  }
}

export interface UncertaintyItem {
  api_path: string
  issues: string[]
}

export interface PlanReviewData {
  id: string
  kind: 'plan_review'
  message: string
  data: {
    memory_dir: string
    error?: string
  }
}

export interface AgentPromptEvent {
  type: 'prompt'
  id: string
  kind: 'api_clarification' | 'plan_review'
  message: string
  data: any
  ts: string
}

export interface AgentCompleteEvent {
  type: 'complete'
  data: CompletionSummary
  ts: string
}

export interface AgentErrorEvent {
  type: 'error'
  message: string
  ts: string
}

export interface CompletionSummary {
  single_cases: number
  biz_flows: number
  interfaces: number
  output_dir: string
  cases_dir: string
  memory_dir: string
}

export type AgentEvent =
  | AgentLogEvent
  | AgentProgressEvent
  | AgentPromptEvent
  | AgentCompleteEvent
  | AgentErrorEvent

// ============================================================================
// Commands (to agent stdin) / 命令（发送到 agent stdin）
// ============================================================================

export type AgentCommand =
  | { command: 'skip'; prompt_id: string }
  | { command: 'respond'; prompt_id: string; text: string }
  | { command: 'approve'; prompt_id: string }
  | { command: 'revise_annotations'; prompt_id: string }
  | { command: 'revise_text'; prompt_id: string; text: string }
  | { command: 'terminate'; prompt_id: string }

// ============================================================================
// plan_sections.json types — 对应 agent/schemas/plan_sections.schema.json
// plan_sections.json types — matching agent/schemas/plan_sections.schema.json
// ============================================================================

/** 单接口用例 section / Single API test case section */
export interface ApiSection {
  chunk_id: string
  key: string
  type: 'api'
  name: string
  section: 'single_api'
  content: string       // markdown，不含 Mermaid
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
  content: string       // markdown，不含 Mermaid
  mermaid: string       // Mermaid 流程图
  involved_apis?: string[]  // 该流涉及的接口 test_id 列表。fix/重画 Mermaid 时查 InterfaceDef / Interface test_ids; used in fix/mermaid regen
  description?: string      // 该流的文字描述。fix/重画 Mermaid 时 LLM prompt 上下文 / Flow description; used as LLM prompt context
}

/** plan_sections.json 顶层结构 / Top-level structure */
export interface PlanSections {
  business_understanding: string
  single_api: ApiSection[]
  biz_flows: BizSection[]
}

/** 从 sections 组装 plan.md（含 chunk 边界标记） / Assemble plan.md from sections (with chunk boundary markers) */
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
