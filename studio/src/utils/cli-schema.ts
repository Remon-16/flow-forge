// CLI 参数 schema 类型定义与查询函数（studio 端）。
// CLI argument schema type definitions and query functions (studio side).
//
// 从 @flow-forge-schemas 共享包导入 schema 数据和类型定义，
// 与 Python 端 shared/py/flow_forge_schemas/cli.py 保持同步。
// 新增参数时只需修改 shared/schemas/cli/*.json。
// Schema data and types imported from @flow-forge-schemas shared package,
// kept in sync with Python side cli.py.
// Only JSON schemas need to be edited when adding/removing args.

import type { CliSchema } from '@flow-forge-schemas'
import { CLI_SCHEMAS } from '@flow-forge-schemas'

// 本地别名，与原有函数签名兼容 / Local alias for backward-compatible function signatures
const SCHEMAS = CLI_SCHEMAS

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
