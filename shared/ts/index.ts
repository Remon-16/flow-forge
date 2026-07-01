// 读取 shared/schemas/ 下的 JSON 数据文件，构造 TypeScript 常量。
// Load JSON data files from shared/schemas/ and construct TypeScript constants.

import columns from '../../schemas/columns.json'
import fieldMapping from '../../schemas/field-mapping.json'
import constants from '../../schemas/constants.json'
import operators from '../../schemas/operators.json'

// ============================================================================
// Excel 列头定义 / Excel column definitions
// ============================================================================

// 接口定义列（13 列） / Interface definition columns (13 columns)
export const API_COLUMNS: readonly string[] = columns.api

// 单接口用例列（15 列） / Single case columns (15 columns)
export const CASE_COLUMNS: readonly string[] = columns.case

// 业务链路步骤列（16 列） / Biz flow step columns (16 columns)
export const BIZ_COLUMNS: readonly string[] = columns.biz

// ============================================================================
// 字段名映射 / Field name mapping
// ============================================================================

// snake_case → PascalCase
export const SNAKE_TO_PASCAL: Record<string, string> = fieldMapping.snake_to_pascal

// PascalCase → snake_case
export const PASCAL_TO_SNAKE: Record<string, string> =
  Object.fromEntries(Object.entries(fieldMapping.snake_to_pascal).map(([k, v]) => [v, k]))

// JSON 列字段 — 在 Excel 中存为 JSON 字符串，在内存中为 dict/list
// JSON column fields — stored as JSON strings in Excel, dict/list in memory
export const JSON_FIELDS: readonly string[] = fieldMapping.json_fields

// ============================================================================
// 校验常量 / Validation constants
// ============================================================================

// 合法 HTTP 方法 / Valid HTTP methods
export const HTTP_METHODS: readonly string[] = constants.http_methods

// 合法 Tag 等级（strict，仅 P0-P3） / Valid tag levels (strict)
export const VALID_TAGS: readonly string[] = constants.valid_tags

// Tag 等级列表（含 P4，用于编辑器下拉） / Tag level list (includes P4, for editor dropdown)
export const TAG_LEVELS: readonly string[] = constants.tag_levels

// 单接口用例必填字段 / Required fields for single test case
export const REQUIRED_SINGLE: readonly string[] = constants.required_single

// 业务链路步骤必填字段 / Required fields for biz flow step
export const REQUIRED_BIZ_STEP: readonly string[] = constants.required_biz_step

// 业务链路必填字段 / Required fields for biz flow
export const REQUIRED_BIZ_FLOW: readonly string[] = constants.required_biz_flow

// ============================================================================
// 断言规则运算符 / Assertion rule operators
// ============================================================================

export interface OperatorDef {
  name: string
  pattern: string
}

// 运算符列表（按优先级排序） / Operator list (priority-ordered)
export const OPERATOR_LIST: readonly OperatorDef[] = operators.operators

// 合法函数 / Valid functions in assertion expressions
export const VALID_FUNCTIONS: readonly string[] = operators.valid_functions

// typeof 合法类型 / Valid types for typeof operator
export const VALID_TYPES: readonly string[] = operators.valid_types
