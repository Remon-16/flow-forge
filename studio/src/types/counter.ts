// Counter Types — 诊断计数器类型定义。
// Diagnostic counter type definitions for session state.
// 对应 executor.ts 的简化版 / Simplified version of executor types.

import type { LogEntry } from './agent'

// ============================================================================
// 会话状态 / Session Status
// ============================================================================

/** 计数器会话状态 / Counter session status */
export type CounterStatus = 'pending' | 'running' | 'completed' | 'error'

// ============================================================================
// 计数器会话 / Counter Session
// ============================================================================

/**
 * 一次诊断计数器会话。
 * A diagnostic counter session — one run of the counter script.
 */
export interface CounterSession {
  /** 会话唯一 ID / Unique session ID */
  id: string
  /** 显示名称 / Display name */
  name: string
  /** 当前状态 / Current status */
  status: CounterStatus
  /** 创建时间戳 / Creation timestamp */
  createdAt: number
  /** 最后更新时间戳 / Last update timestamp */
  updatedAt: number
  /** 输出目录 / Output directory */
  outputDir: string
  /** 日志行列表 / Log lines */
  logLines: LogEntry[]
  /** 完成时的总计数（从 stdout JSON 解析）/ Total counts on completion (parsed from stdout JSON) */
  totalCounts?: number
  /** 错误信息 / Error message */
  error?: string
}
