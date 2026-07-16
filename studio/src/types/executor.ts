// Executor Types — 用例执行器类型定义。
// Executor type definitions for session state, settings, and subprocess events.

import type { LogEntry } from './agent'

// ============================================================================
// 会话状态 / Session Status
// ============================================================================

/** 执行器会话状态。比 Agent 简单，无交互式 prompt。 */
export type ExecutorStatus = 'pending' | 'running' | 'completed' | 'error'

// ============================================================================
// 执行器会话 / Executor Session
// ============================================================================

/**
 * 一次执行器会话。
 * An executor session — one run of the test executor.
 */
export interface ExecutorSession {
  /** 会话唯一 ID / Unique session ID */
  id: string
  /** 显示名称（输出目录基础名） / Display name (output dir basename) */
  name: string
  /** 当前状态 / Current status */
  status: ExecutorStatus
  /** 创建时间戳 / Creation timestamp */
  createdAt: number
  /** 最后更新时间戳 / Last update timestamp */
  updatedAt: number

  // ---- 执行配置 / Execution config ----

  /** 选中的环境后缀，如 "local", "" 表示默认 env.yml / Selected env suffix */
  envSuffix: string
  /** 用例文件路径（Excel） / Case file path (Excel) */
  caseFilePath: string
  /** YAML 目录路径 / YAML directory path */
  yamlDir: string
  /** YAML 文件列表（逗号分隔） / YAML file list (comma-separated) */
  yamlFiles: string
  /** Block1: env-only 参数，始终写入 env 文件 / Env-only params, always written to env */
  envOnlyParams: Record<string, unknown>
  /** Block2: CLI 可用参数，受同步开关控制 / CLI-available params, controlled by save-to-env toggle */
  cliParams: ExecutorCliParams

  // ---- 运行时数据 / Runtime data ----

  /** 日志行列表 / Log lines */
  logLines: LogEntry[]
  /** 测试报告路径（从 stdout JSON 解析） / Test report path (parsed from stdout JSON) */
  reportPath?: string
  /** 执行统计（从 stdout JSON 解析） / Execution stats (parsed from stdout JSON) */
  summary?: ExecutorSummary
  /** 错误信息 / Error message */
  error?: string
}

// ============================================================================
// CLI 参数 / CLI Parameters
// ============================================================================

/** Block2: 可通过 CLI 传递的执行器参数。 */
export interface ExecutorCliParams {
  scriptType: string
  envName: string
  maxThread: number
  reportName: string
  apiMode: string
}

/** 默认 CLI 参数 / Default CLI params */
export const DEFAULT_CLI_PARAMS: ExecutorCliParams = {
  scriptType: 'APITest',
  envName: 'local',
  maxThread: 5,
  reportName: 'APIReport',
  apiMode: 'all',
}

// ============================================================================
// 执行统计 / Execution Summary
// ============================================================================

/** 从 executor stdout JSON 行解析的执行统计。 */
export interface ExecutorSummary {
  single_cases: number
  biz_flows: number
  single_passed: number
  biz_passed: number
}

// ============================================================================
// 执行器设置（持久化到磁盘） / Executor Settings (persisted)
// ============================================================================

/**
 * 执行器持久化设置。
 * Executor settings persisted by Studio.
 */
export interface ExecutorSettings {
  /** 执行器代码根目录 / Executor code root directory */
  executorRootDir: string
}

/** 默认设置 / Default settings */
export const DEFAULT_EXECUTOR_SETTINGS: ExecutorSettings = {
  executorRootDir: '',
}
