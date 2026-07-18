// CLI 参数 schema 类型定义与查询函数（studio 端）。
// CLI argument schema type definitions and query functions (studio side).
//
// 从 shared/schemas/cli/*.json 读取参数定义，与 Python 端 shared/py/flow_forge_schemas/cli.py
// 保持同步。新增参数时只需修改 JSON schema。
// Reads from shared/schemas/cli/*.json; kept in sync with Python cli.py.
// Only JSON schemas need to be edited when adding/removing args.

import agentCli from '../../../shared/schemas/cli/agent.json'
import executorCli from '../../../shared/schemas/cli/executor.json'
import converterCli from '../../../shared/schemas/cli/converter.json'

// ============================================================================
// 类型定义 / Type definitions
// ============================================================================

/** 单个 CLI 参数定义 / Single CLI argument definition */
export interface CliArgDef {
  flag: string
  short: string | null
  dest: string
  type: string
  choices?: string[]
  nargs?: string
  default?: unknown
  required?: boolean
  help_zh: string
  help_en: string
  section?: string | null
  studio: { editable: boolean; field_type?: string }
}

/** 子命令定义 / Subcommand definition */
export interface SubcommandDef {
  description_zh: string
  description_en: string
  args: CliArgDef[]
}

/** CLI Schema 顶层结构 / CLI Schema top-level structure */
export interface CliSchema {
  entry: string
  description_zh: string
  description_en: string
  flag_style: string
  args?: CliArgDef[]
  subcommands?: Record<string, SubcommandDef>
}

// ============================================================================
// Schema 注册表 / Schema registry
// ============================================================================

const SCHEMAS: Record<string, CliSchema> = {
  agent: agentCli as CliSchema,
  executor: executorCli as CliSchema,
  converter: converterCli as CliSchema,
}

// ============================================================================
// 查询函数 / Query functions
// ============================================================================

/**
 * 获取某 entry 某 section 下所有 studio 可编辑的参数 dest 集合。
 * 用于 NewTaskForm.loadYamlConfig() 过滤 env.yaml → ConfigPanel 只显示有 CLI 映射的字段。
 *
 * Get the set of studio-editable arg dests for a section in an entry.
 * Used by NewTaskForm to filter env.yaml pipeline keys for ConfigPanel display.
 */
export function getEditableDestSet(entry: string, section: string): Set<string> {
  const schema = SCHEMAS[entry]
  if (!schema) return new Set()
  const result = new Set<string>()
  for (const a of schema.args ?? []) {
    if (a.studio?.editable && a.section === section) {
      result.add(a.dest)
    }
  }
  return result
}

/**
 * 获取某 entry 某 section 下所有参数的 CLI flag 映射表（dest → flag）。
 * 用于 handleSubmit 将 configOverrides 转换为 CLI 参数。
 *
 * Get CLI flag mapping (dest → flag) for a section in an entry.
 * Used by handleSubmit to convert configOverrides to CLI args.
 */
export function getFlagMap(entry: string, section: string): Map<string, string> {
  const schema = SCHEMAS[entry]
  if (!schema) return new Map()
  const result = new Map<string, string>()
  for (const a of schema.args ?? []) {
    if (a.section === section && a.studio?.editable) {
      result.set(a.dest, a.flag)
    }
  }
  return result
}

/**
 * 获取某 entry 的 CLI schema 对象。
 * Get the full CLI schema for an entry.
 */
export function getCliSchema(entry: string): CliSchema | undefined {
  return SCHEMAS[entry]
}

/**
 * 检查某参数是否不应由 studio 传入（内部/系统参数）。
 * Check if a dest is an internal/system arg that studio should NOT pass.
 */
export function isInternalArg(entry: string, dest: string): boolean {
  const schema = SCHEMAS[entry]
  if (!schema) return true
  const arg = (schema.args ?? []).find(a => a.dest === dest)
  return !arg || !arg.studio?.editable
}
