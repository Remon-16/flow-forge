// ============================================================
// Core data types for the test case Excel workbook
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

// --- Processor types ---

export interface PreProcessorItem {
  name: string
  config?: Record<string, string> | null
}

export type PostProcessorItem = PreProcessorItem

// --- Constants ---

export const HTTP_METHODS = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS']
export const TAG_LEVELS = ['P0', 'P1', 'P2', 'P3', 'P4']

// --- Validation ---

export interface ValidationError {
  sheet: string
  row: number
  field: string
  message: string
}
