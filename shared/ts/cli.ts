// CLI 参数 schema 类型定义与查询函数。
// CLI argument schema type definitions and query functions.
//
// 从 shared/schemas/cli/*.json 读取参数定义，提供类型安全的访问接口，
// 确保 TypeScript 端与 Python 端参数一致。
// Reads arg definitions from shared/schemas/cli/*.json and provides
// type-safe accessors, keeping TypeScript and Python arg lists in sync.

import agentCli from '../schemas/cli/agent.json'
import executorCli from '../schemas/cli/executor.json'
import converterCli from '../schemas/cli/converter.json'

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
// Schema 注册表（所有 3 个入口的最新真相来源）
// Schema registry (single source of truth for all 3 entries)
// ============================================================================

export const CLI_SCHEMAS: Record<string, CliSchema> = {
  agent: agentCli as CliSchema,
  executor: executorCli as CliSchema,
  converter: converterCli as CliSchema,
}

// ============================================================================
// 查询函数 / Query functions
// ============================================================================

/**
 * 获取某个入口的 CLI schema。
 * Get CLI schema for an entry.
 */
export function getCliSchema(entry: 'agent' | 'executor' | 'converter'): CliSchema {
  return CLI_SCHEMAS[entry]
}

/**
 * 获取某 entry 某 section 下所有 studio 可编辑的参数 dest 集合。
 * 用于前端 filtering env.yaml 配置 → ConfigPanel 只显示有 CLI 映射的字段。
 *
 * Get the set of studio-editable arg dests for a section in an entry.
 * Used by frontend to filter env.yaml config → ConfigPanel shows only CLI-mapped fields.
 */
export function getEditableDestSet(entry: string, section: string): Set<string> {
  const schema = CLI_SCHEMAS[entry]
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
 * 获取某 entry 中所有 studio 可编辑的参数。
 * Get all studio-editable args for an entry.
 */
export function getEditableArgs(entry: string): CliArgDef[] {
  const schema = CLI_SCHEMAS[entry]
  if (!schema) return []
  if (schema.subcommands) {
    // Converter：展平所有子命令的参数 / Flatten args from all subcommands
    const result: CliArgDef[] = []
    for (const sc of Object.values(schema.subcommands)) {
      for (const a of sc.args) {
        if (a.studio?.editable) result.push(a)
      }
    }
    return result
  }
  return (schema.args ?? []).filter(a => a.studio?.editable)
}

/**
 * 获取某 entry 中所有内部参数（section 为 null 且 studio 不可编辑）。
 * 这些参数不应由 studio 前端传入。
 *
 * Get all internal args (section=null and studio not editable) for an entry.
 * These args should NOT be passed by the studio frontend.
 */
export function getInternalDestSet(entry: string): Set<string> {
  const schema = CLI_SCHEMAS[entry]
  if (!schema) return new Set()
  const result = new Set<string>()
  for (const a of schema.args ?? []) {
    if (!a.studio?.editable) {
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
  const schema = CLI_SCHEMAS[entry]
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
 * 将 key（下划线命名）转换为 CLI flag（kebab-case）。
 * Convert key (snake_case) to CLI flag (kebab-case).
 */
export function keyToFlag(key: string, _schema: CliSchema): string {
  return `--${key.replace(/_/g, '-')}`
}

/**
 * 检查变量是否应生成 CLI 参数（非空且非 undefined/null）。
 * Check if a value should generate a CLI arg (non-empty, non-null/undefined).
 */
export function shouldPushCliArg(val: unknown): boolean {
  return val !== undefined && val !== null && val !== ''
}
