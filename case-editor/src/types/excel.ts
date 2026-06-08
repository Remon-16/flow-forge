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
  TestID: string
  APIName: string
  AppName: string
  Method: string
  URL: string
  RequestHead: Record<string, unknown>
  RequestBody: Record<string, unknown>
  StatusCode: number | string
  AssertDict: Record<string, unknown>
  Remark: string
}

export interface SingleTestCase {
  TestID: string
  RelevanceID: string
  Tag: string
  APIName: string
  AppName: string
  Method: string
  URL: string
  RequestHead: Record<string, unknown>
  RequestBody: Record<string, unknown>
  StatusCode: number | string
  AssertDict: Record<string, unknown>
  Remark: string
  _relevanceValid?: boolean
}

export interface BizStep {
  StepID: string
  RelevanceID: string
  Trans: string
  APIName: string
  AppName: string
  Method: string
  URL: string
  RequestHead: Record<string, unknown>
  RequestBody: Record<string, unknown>
  StatusCode: number | string
  AssertDict: Record<string, unknown>
  Tag: string
  Remark: string
  _relevanceValid?: boolean
  _stepIdDuplicate?: boolean
  _transError?: string | null
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

// --- Column definitions ---

export const API_DEF_COLUMNS = [
  'TestID', 'APIName', 'AppName', 'Method', 'URL',
  'RequestHead', 'RequestBody', 'StatusCode', 'AssertDict', 'Remark',
] as const

export const SINGLE_CASE_COLUMNS = [
  'TestID', 'RelevanceID', 'Tag', 'APIName', 'AppName', 'Method', 'URL',
  'RequestHead', 'RequestBody', 'StatusCode', 'AssertDict', 'Remark',
] as const

export const BIZ_STEP_COLUMNS = [
  'StepID', 'RelevanceID', 'Trans', 'APIName', 'AppName', 'Method', 'URL',
  'RequestHead', 'RequestBody', 'StatusCode', 'AssertDict', 'Tag', 'Remark',
] as const

export const JSON_COLUMNS = ['RequestHead', 'RequestBody', 'AssertDict'] as const

export const HTTP_METHODS = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS']
export const TAG_LEVELS = ['P0', 'P1', 'P2', 'P3', 'P4']

// --- Validation ---

export interface ValidationError {
  sheet: string
  row: number
  field: string
  message: string
}
