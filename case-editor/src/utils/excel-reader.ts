import * as XLSX from 'xlsx'
import type {
  ApiDefinition,
  SingleTestCase,
  BizStep,
  BizFlow,
  WorkbookData,
} from '../types/excel'
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
 */
export function parseWorkbook(wb: XLSX.WorkBook): WorkbookData {
  const sheetNames = wb.SheetNames

  if (sheetNames.length < 2) {
    throw new Error(`Excel file needs at least 2 sheets, got ${sheetNames.length}`)
  }

  // Sheet 0: API Definitions
  const apiDefs = readSheetRows<ApiDefinition>(wb.Sheets[sheetNames[0]])

  // Sheet 1: Single Test Cases
  const singleCases = readSheetRows<SingleTestCase>(wb.Sheets[sheetNames[1]])

  // Sheets 2+: Biz flows
  const bizFlows: BizFlow[] = []
  for (let i = 2; i < sheetNames.length; i++) {
    const rawSteps = readSheetRows<BizStep>(wb.Sheets[sheetNames[i]])
    bizFlows.push({
      sheetName: sheetNames[i],
      steps: rawSteps,
    })
  }

  return {
    apiDefinitions: apiDefs,
    singleCases,
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
    for (const field of ['RequestHead', 'RequestBody', 'AssertDict']) {
      if (field in cleaned) {
        cleaned[field] = safeParseJson(cleaned[field])
      }
    }
    // Parse AssertRules column: JSON string array to string[]
    if ('AssertRules' in cleaned) {
      cleaned['AssertRules'] = safeParseJsonArray(cleaned['AssertRules'])
    }
    return cleaned as unknown as T
  })
}

/**
 * Safely parse a value to a JSON object. Returns null for empty input.
 */
function safeParseJson(raw: unknown): Record<string, unknown> | null {
  if (raw === null || raw === undefined) return null
  if (typeof raw === 'object' && !Array.isArray(raw)) return raw as Record<string, unknown>
  if (typeof raw === 'string') {
    const stripped = raw.trim()
    if (!stripped) return null
    try {
      // Normalize smart quotes to straight quotes
      const normalized = stripped
        .replace(/“/g, '"')
        .replace(/”/g, '"')
        .replace(/‘/g, '"')
        .replace(/’/g, '"')
        .replace(/'/g, '"')
      return JSON.parse(normalized)
    } catch {
      console.warn(`Failed to parse JSON: ${stripped.slice(0, 100)}`)
      return null
    }
  }
  return null
}

/**
 * Safely parse a value to a string array. Returns null for empty input.
 */
function safeParseJsonArray(raw: unknown): string[] | null {
  if (raw === null || raw === undefined) return null
  if (Array.isArray(raw)) return raw as string[]
  if (typeof raw === 'string') {
    const stripped = raw.trim()
    if (!stripped) return null
    try {
      const normalized = stripped
        .replace(/“/g, '"')
        .replace(/”/g, '"')
        .replace(/‘/g, '"')
        .replace(/’/g, '"')
        .replace(/'/g, '"')
      const parsed = JSON.parse(normalized)
      if (Array.isArray(parsed)) return parsed as string[]
      return null
    } catch {
      console.warn(`Failed to parse AssertRules JSON: ${stripped.slice(0, 100)}`)
      return null
    }
  }
  return null
}
