// Converter Types — 用例转换器类型定义。
// Converter type definitions for session state and events.

import type { LogEntry } from './agent'

// ============================================================================
// 会话状态 / Session Status
// ============================================================================

/** 转换器会话状态。 */
export type ConverterStatus = 'pending' | 'running' | 'completed' | 'error'

// ============================================================================
// 转换方向 / Conversion Direction
// ============================================================================

/** 转换器支持的 4 种子命令。 */
export type ConverterDirection = 'excel2yaml' | 'yaml2excel' | 'yaml2pytest' | 'excel2pytest'

/** 转换方向选项（供下拉菜单使用） / Direction options for dropdown */
export const CONVERTER_DIRECTIONS: { value: ConverterDirection; label: string }[] = [
  { value: 'excel2yaml', label: 'Excel → YAML' },
  { value: 'yaml2excel', label: 'YAML → Excel' },
  { value: 'yaml2pytest', label: 'YAML → pytest' },
  { value: 'excel2pytest', label: 'Excel → pytest' },
]

// ============================================================================
// 编辑器转换参数（从编辑器工具栏设置）/ Editor Converter Params (from editor toolbar)
// ============================================================================

/** 编辑器保存的转换参数 / Converter params saved from editor */
export interface EditorConverterParams {
  direction: ConverterDirection
  outputPath: string
}

/** 编辑器转换参数默认值 / Default editor converter params */
export const DEFAULT_EDITOR_CONVERTER_PARAMS: EditorConverterParams = {
  direction: 'excel2yaml',
  outputPath: '',
}

// ============================================================================
// 转换器会话 / Converter Session
// ============================================================================

/**
 * 一次转换器会话。
 * A converter session — one format conversion run.
 */
export interface ConverterSession {
  /** 会话唯一 ID / Unique session ID */
  id: string
  /** 显示名称 / Display name */
  name: string
  /** 当前状态 / Current status */
  status: ConverterStatus
  /** 转换方向 / Conversion direction */
  direction: ConverterDirection
  /** 创建时间戳 / Creation timestamp */
  createdAt: number
  /** 最后更新时间戳 / Last update timestamp */
  updatedAt: number

  // ---- 输入/输出路径 / Input/Output paths ----

  /** 输入文件路径（excel2yaml / excel2pytest） / Input file path */
  inputPath: string
  /** interfaces 目录（yaml2excel / yaml2pytest） / Interfaces directory */
  interfacesDir: string
  /** single_cases 目录 / Single cases directory */
  singleCasesDir: string
  /** biz_flows 目录 / Biz flows directory */
  bizFlowsDir: string
  /** 输出路径 / Output path */
  outputPath: string
  /** config 目录（pytest 转换用） / Config directory (for pytest conversion) */
  configDir: string
  /** processors 目录（pytest 转换用） / Processors directory (for pytest conversion) */
  processorsDir: string

  // ---- 运行时数据 / Runtime data ----

  /** 日志行列表 / Log lines */
  logLines: LogEntry[]
  /** 输出结果路径（从 stdout JSON 解析） / Output path (parsed from stdout JSON) */
  outputLinkPath?: string
  /** 错误信息 / Error message */
  error?: string
}
