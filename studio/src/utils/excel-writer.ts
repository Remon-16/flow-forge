import ExcelJS from 'exceljs'
import type { WorkbookData } from '../types/excel'
import {
  API_DEF_COLUMNS,
  SINGLE_CASE_COLUMNS,
  BIZ_STEP_COLUMNS,
  JSON_COLUMNS,
} from '../types/excel'

// --- Style constants (mirror agent/agents/excel_writer.py) ---

const HEADER_FONT: Partial<ExcelJS.Font> = {
  name: '微软雅黑',
  bold: true,
  size: 11,
  color: { argb: 'FFFFFFFF' },
}

const HEADER_FILL: ExcelJS.Fill = {
  type: 'pattern',
  pattern: 'solid',
  fgColor: { argb: 'FF4472C4' },
}

const HEADER_ALIGNMENT: Partial<ExcelJS.Alignment> = {
  horizontal: 'center',
  vertical: 'middle',
}

const DATA_FONT: Partial<ExcelJS.Font> = {
  name: '微软雅黑',
  size: 10,
}

const DATA_ALIGNMENT: Partial<ExcelJS.Alignment> = {
  vertical: 'top',
  wrapText: true,
}

const THIN_BORDER: Partial<ExcelJS.Borders> = {
  top: { style: 'thin' },
  left: { style: 'thin' },
  bottom: { style: 'thin' },
  right: { style: 'thin' },
}

// --- Helpers ---

const INTERNAL_FIELDS = ['_uid', '_relevanceValid', '_stepIdDuplicate', '_inheritError']

function safeSheetName(name: string): string {
  return name
    .replace(/[:\\/*?]/g, '-')
    .replace(/[[\]]/g, '')
    .slice(0, 31)
}

function serializeCellValue(val: unknown): string {
  if (val === null || val === undefined) return ''
  if (typeof val === 'object') return JSON.stringify(val)
  return String(val)
}

function applyHeaderStyle(cell: ExcelJS.Cell) {
  cell.font = HEADER_FONT
  cell.fill = HEADER_FILL
  cell.alignment = HEADER_ALIGNMENT
  cell.border = THIN_BORDER
}

function applyDataStyle(cell: ExcelJS.Cell) {
  cell.font = DATA_FONT
  cell.alignment = DATA_ALIGNMENT
  cell.border = THIN_BORDER
}

function autoWidth(ws: ExcelJS.Worksheet) {
  ws.columns.forEach((col, i) => {
    let maxLen = 0
    ws.eachRow({ includeEmpty: true }, (row) => {
      const cell = row.getCell(i + 1)
      const v = cell.value
      if (v != null) {
        // ExcelJS rich text uses array form
        const text = typeof v === 'object' && 'richText' in v
          ? (v as { richText: Array<{ text: string }> }).richText.map(t => t.text).join('')
          : typeof v === 'object'
            ? JSON.stringify(v)
            : String(v)
        // Estimate: CJK chars count as ~2, ASCII as 1
        let len = 0
        for (const ch of text) {
          len += ch.charCodeAt(0) > 127 ? 2 : 1
        }
        maxLen = Math.max(maxLen, len)
      }
    })
    col.width = Math.min(maxLen + 4, 60)
    // Minimum width guard
    if (col.width < 10) col.width = 10
  })
}

// --- Public API ---

export async function createWorkbook(data: WorkbookData): Promise<ExcelJS.Workbook> {
  const wb = new ExcelJS.Workbook()

  // Sheet 0: API Definitions
  const wsApi = wb.addWorksheet('API Definitions')
  writeSheetWithColumns(wsApi, data.apiDefinitions, API_DEF_COLUMNS as unknown as string[])

  // Sheet 1: Single Cases
  const wsSingle = wb.addWorksheet('Single Cases')
  writeSheetWithColumns(wsSingle, data.singleCases, SINGLE_CASE_COLUMNS as unknown as string[])

  // Sheets 2+: Biz Flows
  for (const flow of data.bizFlows) {
    const wsBiz = wb.addWorksheet(safeSheetName(flow.sheetName))
    writeSheetWithColumns(wsBiz, flow.steps, BIZ_STEP_COLUMNS as unknown as string[])
  }

  return wb
}

function writeSheetWithColumns(
  ws: ExcelJS.Worksheet,
  rows: Record<string, unknown>[],
  columns: string[],
) {
  // Header row
  const headerRow = ws.addRow(columns)
  headerRow.eachCell((cell) => applyHeaderStyle(cell))

  // Data rows
  for (const row of rows) {
    const jsonValues: Record<string, string> = {}
    const values = columns.map((col) => {
      if ((JSON_COLUMNS as readonly string[]).includes(col)) {
        const v = row[col]
        const str = v && typeof v === 'object' ? JSON.stringify(v, null, 2) : (v ?? '')
        jsonValues[col] = String(str)
        return str
      }
      if (INTERNAL_FIELDS.includes(col)) return ''
      return serializeCellValue(row[col])
    })
    const dataRow = ws.addRow(values)
    dataRow.eachCell((cell) => applyDataStyle(cell))

    let maxLines = 1
    for (const val of Object.values(jsonValues)) {
      if (typeof val === 'string') {
        maxLines = Math.max(maxLines, val.split('\n').length)
      }
    }
    dataRow.height = maxLines * 15
  }

  autoWidth(ws)
}

/**
 * Trigger a browser file-save dialog for the workbook.
 */
export async function downloadExcel(data: WorkbookData, fileName: string): Promise<void> {
  const wb = await createWorkbook(data)
  const buffer = await wb.xlsx.writeBuffer()
  const blob = new Blob([buffer], {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = fileName
  a.click()
  URL.revokeObjectURL(url)
}

/**
 * Write WorkbookData to an Excel file at the given path (Node.js only).
 */
export async function writeExcel(filePath: string, data: WorkbookData): Promise<void> {
  const wb = await createWorkbook(data)
  await wb.xlsx.writeFile(filePath)
}
