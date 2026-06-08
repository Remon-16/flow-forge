import * as XLSX from 'xlsx'
import { workbookDataToXlsx } from './excel-reader'
import type { WorkbookData } from '../types/excel'

/**
 * Write WorkbookData to an Excel file at the given path.
 */
export function writeExcel(filePath: string, data: WorkbookData): void {
  const wb = workbookDataToXlsx(data)
  XLSX.writeFile(wb, filePath)
}

/**
 * Trigger a browser file-save dialog for the workbook.
 */
export function downloadExcel(data: WorkbookData, fileName: string): void {
  const wb = workbookDataToXlsx(data)
  XLSX.writeFile(wb, fileName)
}
