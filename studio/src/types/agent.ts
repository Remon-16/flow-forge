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
// Agent Settings / 智能体设置
// ============================================================================

export interface AgentConfig {
  agentRootDir: string
  configFileName: string       // default: env.yaml
  pythonExePath: string        // optional
  venvPath: string             // optional
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
    plan_preview: string
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
