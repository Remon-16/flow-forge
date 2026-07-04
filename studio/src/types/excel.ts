// ============================================================
// Core data types for the test case Excel workbook
// 规范字段定义 / Canonical field definitions:
// shared/schemas/types.json (interface_def, single_test_case, biz_step, biz_flow)
// ============================================================

export type JsonType = 'string' | 'number' | 'boolean' | 'Date' | 'List' | 'Dict'

export interface JsonNode {
  key: string
  type: JsonType
  value: string | number | boolean | string | JsonNode[] | Record<string, JsonNode>
}

// --- Row-level types matching the Excel sheets ---

export interface ApiDefinition {
  [key: string]: unknown
  _uid: string
  TestID: string
  APIName: string
  AppName: string
  Method: string
  URL: string
  RequestHead: Record<string, unknown> | null
  RequestBody: Record<string, unknown> | null
  StatusCode: number | string
  AssertDict: Record<string, unknown> | null
  AssertRules: string[] | null
  PreProcessors: PreProcessorItem[] | null
  PostProcessors: PostProcessorItem[] | null
  Remark: string
}

export interface SingleTestCase {
  [key: string]: unknown
  _uid: string
  TestID: string
  RelevanceID: string
  Tag: string
  APIName: string
  AppName: string
  Method: string
  URL: string
  RequestHead: Record<string, unknown> | null
  RequestBody: Record<string, unknown> | null
  StatusCode: number | string
  AssertDict: Record<string, unknown> | null
  AssertRules: string[] | null
  PreProcessors: PreProcessorItem[] | null
  PostProcessors: PostProcessorItem[] | null
  Remark: string
  _relevanceValid?: boolean
}

export interface BizStep {
  [key: string]: unknown
  _uid: string
  StepID: string
  RelevanceID: string
  Inherit: string
  APIName: string
  AppName: string
  Method: string
  URL: string
  RequestHead: Record<string, unknown> | null
  RequestBody: Record<string, unknown> | null
  StatusCode: number | string
  AssertDict: Record<string, unknown> | null
  AssertRules: string[] | null
  PreProcessors: PreProcessorItem[] | null
  PostProcessors: PostProcessorItem[] | null
  Tag: string
  Remark: string
  _relevanceValid?: boolean
  _stepIdDuplicate?: boolean
  _inheritError?: string | null
}

export interface BizFlow {
  sheetName: string
  steps: BizStep[]
}

export interface WorkbookData {
  apiDefinitions: ApiDefinition[]
  singleCases: SingleTestCase[]
  bizFlows: BizFlow[]
}

// --- Column definitions — re-exported from shared schema package ---

export {
  API_COLUMNS as API_DEF_COLUMNS,
  CASE_COLUMNS as SINGLE_CASE_COLUMNS,
  BIZ_COLUMNS as BIZ_STEP_COLUMNS,
  JSON_FIELDS as JSON_COLUMNS,
} from '@flow-forge-schemas'

import { HTTP_METHODS as SCHEMA_HTTP_METHODS, TAG_LEVELS as SCHEMA_TAG_LEVELS } from '@flow-forge-schemas'

// --- Processor types ---

export interface PreProcessorItem {
  name: string
  config?: Record<string, string> | null
}

export type PostProcessorItem = PreProcessorItem

// --- Constants ---

// 基于 shared/schemas/constants.json 扩展，编辑器下拉需 HEAD/OPTIONS
export const HTTP_METHODS: readonly string[] = [...SCHEMA_HTTP_METHODS, 'HEAD', 'OPTIONS']
export const TAG_LEVELS: readonly string[] = SCHEMA_TAG_LEVELS

// --- Validation ---

export interface ValidationError {
  sheet: string
  row: number
  field: string
  message: string
}
