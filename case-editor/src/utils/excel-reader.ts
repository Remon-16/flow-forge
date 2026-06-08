import * as XLSX from 'xlsx'
import type {
  ApiDefinition,
  SingleTestCase,
  BizStep,
  BizFlow,
  WorkbookData,
} from '../types/excel'
import { deepMerge } from './deep-merge'

let uidCounter = 0
function generateUid(): string {
  return `_uid_${Date.now()}_${++uidCounter}`
}

/**
 * Read an Excel file from a file path (Node.js only).
 */
export function readExcel(filePath: string): WorkbookData {
  const wb = XLSX.readFile(filePath)
  return parseWorkbook(wb)
}

/**
 * Read an Excel file from an ArrayBuffer (browser-compatible).
 */
export function readExcelFromBuffer(buffer: ArrayBuffer): WorkbookData {
  const wb = XLSX.read(new Uint8Array(buffer), { type: 'array' })
  return parseWorkbook(wb)
}

/**
 * Parse a workbook object into structured WorkbookData.
 * Aligns with python/excel_reader/excel_parser.py merge logic.
 */
export function parseWorkbook(wb: XLSX.WorkBook): WorkbookData {
  const sheetNames = wb.SheetNames

  if (sheetNames.length < 2) {
    throw new Error(`Excel 文件至少需要 2 个 Sheet，当前只有 ${sheetNames.length} 个`)
  }

  // Sheet 0: API Definitions
  const apiDefs = readSheetRows<ApiDefinition>(wb.Sheets[sheetNames[0]])

  // Sheet 1: Single Test Cases
  const singleCases = readSheetRows<SingleTestCase>(wb.Sheets[sheetNames[1]])

  // Merge single cases with API definitions
  const mergedSingles = singleCases.map((tc) =>
    mergeWithApiDef(tc, apiDefs, false)
  ) as SingleTestCase[]

  // Sheets 2+: Biz flows
  const bizFlows: BizFlow[] = []
  for (let i = 2; i < sheetNames.length; i++) {
    const rawSteps = readSheetRows<BizStep>(wb.Sheets[sheetNames[i]])
    const mergedSteps = rawSteps.map((step) =>
      mergeWithApiDef(step, apiDefs, true)
    ) as BizStep[]
    bizFlows.push({
      sheetName: sheetNames[i],
      steps: mergedSteps,
    })
  }

  return {
    apiDefinitions: apiDefs,
    singleCases: mergedSingles,
    bizFlows,
  }
}

/**
 * Read all rows from a worksheet into an array of typed objects.
 */
function readSheetRows<T>(ws: XLSX.WorkSheet): T[] {
  const raw: Record<string, unknown>[] = XLSX.utils.sheet_to_json(ws, { defval: null })
  return raw.map((row) => {
    const cleaned: Record<string, unknown> = {}
    for (const [key, val] of Object.entries(row)) {
      cleaned[key.trim()] = val
    }
    cleaned._uid = generateUid()
    // 对 JSON 列统一做 safeParseJson，确保字符串被解析为对象
    for (const field of ['RequestHead', 'RequestBody', 'AssertDict']) {
      if (field in cleaned) {
        cleaned[field] = safeParseJson(cleaned[field])
      }
    }
    return cleaned as unknown as T
  })
}

/**
 * Merge a test case / biz step row with the matching API definition.
 * Simple fields: test case wins, API def fills empty.
 * JSON fields: deep merge, test case overrides, API def supplements missing.
 * AssertDict: test case wins if present, else API def.
 */
function mergeWithApiDef(
  tc: Record<string, unknown>,
  apiDefs: ApiDefinition[],
  isBiz: boolean
): Record<string, unknown> {
  const relevanceId = String(tc.RelevanceID ?? '')
  const apiDef = apiDefs.find((a) => a.TestID === relevanceId)

  const simpleFields = ['APIName', 'AppName', 'Method', 'URL', 'StatusCode']
  const jsonFields = ['RequestHead', 'RequestBody']

  const result: Record<string, unknown> = {}

  for (const field of simpleFields) {
    const tcVal = tc[field]
    const apiVal = apiDef ? (apiDef as Record<string, unknown>)[field] : null
    result[field] = tcVal != null && tcVal !== '' ? tcVal : apiVal
  }

  for (const field of jsonFields) {
    const tcJson = safeParseJson(tc[field])
    const apiJson = apiDef ? safeParseJson((apiDef as Record<string, unknown>)[field]) : {}
    result[field] = deepMerge(apiJson, tcJson)
  }

  // AssertDict
  const tcAssert = safeParseJson(tc.AssertDict)
  if (Object.keys(tcAssert).length > 0) {
    result.AssertDict = tcAssert
  } else if (apiDef && apiDef.AssertDict) {
    result.AssertDict = apiDef.AssertDict
  } else {
    result.AssertDict = {}
  }

  // Copy remaining fields
  if (isBiz) {
    result.StepID = tc.StepID ?? ''
    result.Trans = tc.Trans != null ? String(tc.Trans).trim() : ''
  }

  result.TestID = tc.TestID ?? (tc.StepID ?? '')
  result.RelevanceID = tc.RelevanceID ?? ''
  result.Tag = tc.Tag != null ? String(tc.Tag) : ''
  result.Remark = tc.Remark != null ? String(tc.Remark) : ''

  return result
}

/**
 * Safely parse a value to a JSON object. Returns {} on failure.
 */
function safeParseJson(raw: unknown): Record<string, unknown> {
  if (raw === null || raw === undefined) return {}
  if (typeof raw === 'object' && !Array.isArray(raw)) return raw as Record<string, unknown>
  if (typeof raw === 'string') {
    const stripped = raw.trim()
    if (!stripped) return {}
    try {
      // Normalize curly quotes
      const normalized = stripped
        .replace(/“/g, '"')
        .replace(/”/g, '"')
        .replace(/‘/g, '"')
        .replace(/’/g, '"')
        .replace(/'/g, '"')
      return JSON.parse(normalized)
    } catch {
      console.warn(`Failed to parse JSON: ${stripped.slice(0, 100)}`)
      return {}
    }
  }
  return {}
}

/**
 * Convert WorkbookData back to XLSX workbook for download/save.
 */
import type { WorkBook } from 'xlsx'

export function workbookDataToXlsx(data: WorkbookData): WorkBook {
  const wb = XLSX.utils.book_new()

  // Sheet 0: API Definitions
  const apiWs = XLSX.utils.json_to_sheet(
    data.apiDefinitions.map(serializeRow)
  )
  XLSX.utils.book_append_sheet(wb, apiWs, 'API Definitions')

  // Sheet 1: Single Cases
  const singleWs = XLSX.utils.json_to_sheet(
    data.singleCases.map(serializeRow)
  )
  XLSX.utils.book_append_sheet(wb, singleWs, 'Single Cases')

  // Sheets 2+: Biz Flows
  for (const flow of data.bizFlows) {
    const bizWs = XLSX.utils.json_to_sheet(
      flow.steps.map(serializeRow)
    )
    XLSX.utils.book_append_sheet(wb, bizWs, flow.sheetName)
  }

  return wb
}

/**
 * Serialize JSON fields back to strings for Excel output.
 */
function serializeRow(row: Record<string, unknown>): Record<string, unknown> {
  const jsonFields = ['RequestHead', 'RequestBody', 'AssertDict']
  const result = { ...row }
  for (const field of jsonFields) {
    if (result[field] && typeof result[field] === 'object') {
      result[field] = JSON.stringify(result[field])
    }
  }
  // Remove internal editor fields
  delete result._uid
  delete result._relevanceValid
  delete result._stepIdDuplicate
  delete result._transError
  return result
}
