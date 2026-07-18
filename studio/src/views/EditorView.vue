<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { toRaw } from 'vue'
import { useEditorStore } from '../stores/editor'
import { useWorkbookStore } from '../stores/workbook'
import { useExecutorStore } from '../stores/executor'
import { useConverterStore } from '../stores/converter'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { writeFile, deleteToTrash, mkdir } from '../utils/desktop-bridge'
import { getAppDataDir } from '../utils/settings-store'
import yaml from 'js-yaml'
import ApiDefEditor from '../components/editor/ApiDefEditor.vue'
import SingleCaseEditor from '../components/editor/SingleCaseEditor.vue'
import BizFlowEditor from '../components/editor/BizFlowEditor.vue'
import SearchBar from '../components/search/SearchBar.vue'
import SearchResultsPanel from '../components/search/SearchResultsPanel.vue'
import EditorToolbar from '../components/editor/EditorToolbar.vue'
import LogPanel from '../components/editor/LogPanel.vue'
import CaseSelectModal from '../components/editor/CaseSelectModal.vue'
import ParamEditModal from '../components/editor/ParamEditModal.vue'
import type { SearchResultItem } from '../components/search/SearchResultsPanel.vue'
import type { SearchOptions } from '../components/search/SearchBar.vue'

const { t } = useI18n()
const editor = useEditorStore()
const workbook = useWorkbookStore()
const executor = useExecutorStore()
const converter = useConverterStore()

// ============================================================================
// Editor toolbar state / 编辑器工具栏状态
// ============================================================================

const workbookPath = ref('')
const caseSelectVisible = ref(false)
const caseSelectCases = ref<{ id: string; name: string; type: 'single' | 'biz'; sheetName?: string }[]>([])
const paramEditVisible = ref(false)
const paramEditMode = ref<'executor' | 'converter'>('executor')

// Watch for workbook path changes
watch(() => (workbook as any)._filePath, (fp) => {
  workbookPath.value = fp || ''
}, { immediate: true })

// ============================================================================
// Build case list for CaseSelectModal / 构建用例选择列表
// ============================================================================

function buildCaseList() {
  const cases: { id: string; name: string; type: 'single' | 'biz'; sheetName?: string }[] = []

  // Single cases
  for (const c of workbook.singleCases) {
    const name = (c as any).TestID || (c as any).APIName || `Case ${cases.length}`
    cases.push({ id: (c as any)._uid || name, name, type: 'single', sheetName: 'SingleCases' })
  }

  // Biz flows
  for (const flow of workbook.bizFlows) {
    const sheetName = flow.sheetName || 'BizFlow'
    for (const step of flow.steps) {
      const name = (step as any).StepID || (step as any).APIName || `Step ${cases.length}`
      cases.push({ id: (step as any)._uid || name, name, type: 'biz', sheetName })
    }
  }

  return cases
}

// ============================================================================
// Temp YAML generation for executor / 生成临时 YAML 文件供执行器使用
// ============================================================================

async function writeTempYaml(caseFilter: 'all' | 'single' | 'biz' | string[]): Promise<string> {
  const cases: Record<string, unknown>[] = []

  if (caseFilter === 'all' || caseFilter === 'single') {
    for (const c of workbook.singleCases) {
      cases.push(workbookRowToYaml(c, 'single'))
    }
  }

  if (caseFilter === 'all' || caseFilter === 'biz') {
    for (const flow of workbook.bizFlows) {
      const steps = flow.steps.map(s => workbookRowToYaml(s, 'single'))
      cases.push({
        case_type: 'biz',
        sheet_name: flow.sheetName || 'BizFlow',
        steps,
      })
    }
  }

  if (Array.isArray(caseFilter)) {
    // Filter by selected IDs
    const selectedIds = new Set(caseFilter)
    for (const c of workbook.singleCases) {
      const id = (c as any)._uid || ''
      if (selectedIds.has(id)) {
        cases.push(workbookRowToYaml(c, 'single'))
      }
    }
    for (const flow of workbook.bizFlows) {
      const selectedSteps = flow.steps.filter(s => selectedIds.has((s as any)._uid || ''))
      if (selectedSteps.length > 0) {
        cases.push({
          case_type: 'biz',
          sheet_name: flow.sheetName || 'BizFlow',
          steps: selectedSteps.map(s => workbookRowToYaml(s, 'single')),
        })
      }
    }
  }

  const yamlContent = yaml.dump(cases, { indent: 2, lineWidth: -1 })

  // 使用 appDataDir 下的 temp/ 子目录，避免污染源码目录，MSI 安装后也可正常读写
  // Use temp/ subdirectory under appDataDir, works in dev and after MSI install
  const appDir = await getAppDataDir()
  const tempDir = `${appDir}/temp`.replace(/\\/g, '/')
  // 确保 temp 目录存在（首次运行或清理后）/ Ensure temp dir exists (first run or after cleanup)
  await mkdir(tempDir)
  const tempPath = `${tempDir}/_studio_temp_${Date.now()}.yaml`

  // 写入临时文件 / Write temp file
  await writeFile(tempPath, yamlContent)

  // 清理 1 小时前的旧临时文件 / Clean up old temp files (older than 1 hour)
  cleanupOldTempFiles(tempDir).catch(() => {})

  return tempPath
}

/** 清理指定目录中的旧临时文件 / Clean up old temp files in given directory */
async function cleanupOldTempFiles(tempDir: string): Promise<void> {
  try {
    const { listDirectoryAll } = await import('../utils/desktop-bridge')
    const entries = await listDirectoryAll(tempDir)
    const now = Date.now()
    for (const entry of entries) {
      if (entry.name.startsWith('_studio_temp_') && !entry.isDirectory) {
        const match = entry.name.match(/_studio_temp_(\d+)\./)
        if (match) {
          const ts = parseInt(match[1], 10)
          // 删除 1 小时前的文件 / Delete files older than 1 hour
          if (now - ts > 3_600_000) {
            deleteToTrash(entry.path).catch(() => {})
          }
        } else {
          // 无法解析时间戳，直接删除 / Can't parse timestamp, delete anyway
          deleteToTrash(entry.path).catch(() => {})
        }
      }
    }
  } catch { /* 非桌面模式或目录不存在 / Non-desktop mode or dir doesn't exist */ }
}

function workbookRowToYaml(row: unknown, caseType: string): Record<string, unknown> {
  const r = row as Record<string, unknown>
  return {
    case_type: caseType,
    test_id: r['TestID'] || '',
    api_name: r['APIName'] || '',
    app_name: r['AppName'] || '',
    method: r['Method'] || 'GET',
    url: r['URL'] || '',
    request_head: safeJsonParse(r['RequestHead']),
    request_body: safeJsonParse(r['RequestBody']),
    status_code: r['StatusCode'] || 200,
    assert_dict: safeJsonParse(r['AssertDict']),
    assert_rules: safeJsonParse(r['AssertRules']),
    preprocessors: safeJsonParse(r['PreProcessors']),
    postprocessors: safeJsonParse(r['PostProcessors']),
    remark: r['Remark'] || '',
  }
}

function safeJsonParse(val: unknown): unknown {
  if (!val || typeof val !== 'string') return val ?? null
  try { return JSON.parse(val) } catch { return val }
}

// ============================================================================
// Toolbar handlers / 工具栏事件处理
// ============================================================================

async function handleRunAll() {
  try {
    const tempPath = await writeTempYaml('all')
    const sessionId = executor.createSession({
      envSuffix: '',
      caseFilePath: '',
      yamlDir: '',
      yamlFiles: tempPath,
      envOnlyParams: {},
      cliParams: executor.getEditorCliParams(workbookPath.value),
    })
    await executor.startSession(sessionId)
  } catch (e: unknown) {
    message.error(String(e))
  }
}

async function handleRunSingle() {
  try {
    const tempPath = await writeTempYaml('single')
    const sessionId = executor.createSession({
      envSuffix: '',
      caseFilePath: '',
      yamlDir: '',
      yamlFiles: tempPath,
      envOnlyParams: {},
      cliParams: executor.getEditorCliParams(workbookPath.value),
    })
    await executor.startSession(sessionId)
  } catch (e: unknown) {
    message.error(String(e))
  }
}

async function handleRunBiz() {
  try {
    const tempPath = await writeTempYaml('biz')
    const sessionId = executor.createSession({
      envSuffix: '',
      caseFilePath: '',
      yamlDir: '',
      yamlFiles: tempPath,
      envOnlyParams: {},
      cliParams: executor.getEditorCliParams(workbookPath.value),
    })
    await executor.startSession(sessionId)
  } catch (e: unknown) {
    message.error(String(e))
  }
}

function handleRunSelect() {
  caseSelectCases.value = buildCaseList()
  paramEditMode.value = 'executor'
  caseSelectVisible.value = true
}

async function handleCaseSelectConfirm(selectedIds: string[]) {
  if (selectedIds.length === 0) return
  try {
    const tempPath = await writeTempYaml(selectedIds)
    const sessionId = executor.createSession({
      envSuffix: '',
      caseFilePath: '',
      yamlDir: '',
      yamlFiles: tempPath,
      envOnlyParams: {},
      cliParams: executor.getEditorCliParams(workbookPath.value),
    })
    await executor.startSession(sessionId)
  } catch (e: unknown) {
    message.error(String(e))
  }
}

// Converter handlers — 使用当前 Excel 文件路径 / Use current Excel file path
async function handleConvert(direction: 'excel2yaml' | 'yaml2excel' | 'excel2pytest') {
  if (!workbookPath.value) {
    message.warning(t('editor.toolbar.noFile'))
    return
  }
  const outputPath = workbookPath.value.replace(/\.xlsx$/i, '_converted')
  const sessionId = converter.createSession({
    direction,
    inputPath: workbookPath.value,
    outputPath: direction === 'yaml2excel' ? workbookPath.value.replace(/\.xlsx$/i, '_from_yaml.xlsx') : outputPath,
    interfacesDir: '',
    singleCasesDir: '',
    bizFlowsDir: '',
    configDir: '',
    processorsDir: '',
  })
  await converter.startSession(sessionId)
}

function handleConvertAll() {
  handleConvert('excel2yaml')
}

async function handleConvertSingle() {
  if (!workbookPath.value) {
    message.warning(t('editor.toolbar.noFile'))
    return
  }
  try {
    const tempPath = await writeTempYaml('single')
    const tempDir = tempPath.replace(/[/\\][^/\\]+\.yaml$/i, '')
    const sessionId = converter.createSession({
      direction: 'yaml2excel',
      inputPath: '',
      outputPath: workbookPath.value.replace(/\.xlsx$/i, '_single.xlsx'),
      interfacesDir: '',
      singleCasesDir: tempDir,
      bizFlowsDir: '',
      configDir: '',
      processorsDir: '',
    })
    await converter.startSession(sessionId)
  } catch (e: unknown) { message.error(String(e)) }
}

async function handleConvertBiz() {
  if (!workbookPath.value) {
    message.warning(t('editor.toolbar.noFile'))
    return
  }
  try {
    const tempPath = await writeTempYaml('biz')
    const tempDir = tempPath.replace(/[/\\][^/\\]+\.yaml$/i, '')
    const sessionId = converter.createSession({
      direction: 'yaml2excel',
      inputPath: '',
      outputPath: workbookPath.value.replace(/\.xlsx$/i, '_biz.xlsx'),
      interfacesDir: '',
      singleCasesDir: '',
      bizFlowsDir: tempDir,
      configDir: '',
      processorsDir: '',
    })
    await converter.startSession(sessionId)
  } catch (e: unknown) { message.error(String(e)) }
}

function handleConvertSelect() {
  caseSelectCases.value = buildCaseList()
  paramEditMode.value = 'converter'
  caseSelectVisible.value = true
}

async function handleConvertCaseSelectConfirm(selectedIds: string[]) {
  if (selectedIds.length === 0) return
  try {
    const tempPath = await writeTempYaml(selectedIds)
    // 提取 temp 文件所在目录作为 yaml2excel 输入 / Extract temp file dir as yaml2excel input
    const tempDir = tempPath.replace(/[/\\][^/\\]+\.yaml$/i, '')

    // 保存对话框选择输出路径 / Save dialog for output path
    let outputPath = ''
    try {
      const { saveFileDialog } = await import('../utils/desktop-bridge')
      const picked = await saveFileDialog({
        defaultPath: tempDir + '/selected_cases.xlsx',
        filters: [{ name: 'Excel', extensions: ['xlsx'] }],
      })
      if (picked) outputPath = picked
    } catch { /* 浏览器模式或用户取消 / browser mode or cancelled */ }
    if (!outputPath) outputPath = tempDir + '/selected_cases.xlsx'

    const sessionId = converter.createSession({
      direction: 'yaml2excel',
      inputPath: '',
      outputPath,
      interfacesDir: '',
      singleCasesDir: tempDir,
      bizFlowsDir: tempDir,
      configDir: '',
      processorsDir: '',
    })
    await converter.startSession(sessionId)
  } catch (e: unknown) {
    message.error(String(e))
  }
}

function handleEditRunParams() {
  paramEditMode.value = 'executor'
  paramEditVisible.value = true
}

function handleEditConvertParams() {
  paramEditMode.value = 'converter'
  paramEditVisible.value = true
}

// --- Search state ---
const searchVisible = ref(false)
const searchReplaceMode = ref(false)
const searchMatchCount = ref(0)
const searchCurrentMatch = ref(1)
const searchMatches = ref<Array<{ rowIndex: number; colKey: string }>>([])
const lastQuery = ref('')
const lastOptions = ref<SearchOptions>({ matchCase: false, wholeWord: false, regex: false })

function getCurrentSheetData(): Record<string, unknown>[] {
  if (editor.activeSheetIndex === -1) return workbook.apiDefinitions as unknown as Record<string, unknown>[]
  if (editor.activeSheetIndex === 0) return workbook.singleCases as unknown as Record<string, unknown>[]
  const flowIdx = editor.activeSheetIndex - 1
  if (flowIdx >= 0 && flowIdx < workbook.bizFlows.length) {
    return workbook.bizFlows[flowIdx].steps as unknown as Record<string, unknown>[]
  }
  return []
}

function doSearch(query: string, options: SearchOptions) {
  lastQuery.value = query
  lastOptions.value = options
  clearSearchHighlights()
  const rawData = getCurrentSheetData()
  const data = toRaw(rawData) as Record<string, unknown>[]
  const matches: Array<{ rowIndex: number; colKey: string }> = []

  let pattern: RegExp
  try {
    const flags = options.matchCase ? 'g' : 'gi'
    const escaped = options.regex ? query : query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    const source = options.wholeWord ? `\\b${escaped}\\b` : escaped
    pattern = new RegExp(source, flags)
  } catch {
    searchMatchCount.value = 0
    searchCurrentMatch.value = 0
    return
  }

  for (let i = 0; i < data.length; i++) {
    const row = toRaw(data[i]) as Record<string, unknown>
    for (const [key, val] of Object.entries(row)) {
      if (key.startsWith('_')) continue
      const text = valueToSearchText(val)
      if (pattern.test(text)) {
        matches.push({ rowIndex: i, colKey: key })
        pattern.lastIndex = 0
      }
    }
  }

  searchMatches.value = matches
  searchMatchCount.value = matches.length
  searchCurrentMatch.value = matches.length > 0 ? 1 : 0

  // Apply highlights to rows
  const matchRowIndices = new Set(matches.map(m => m.rowIndex))
  for (let i = 0; i < data.length; i++) {
    ;(data[i] as any)._searchMatch = matchRowIndices.has(i)
    ;(data[i] as any)._searchActive = false
  }
  if (matches.length > 0) {
    ;(data[matches[0].rowIndex] as any)._searchActive = true
  }
}

function clearSearchHighlights() {
  const data = getCurrentSheetData()
  for (const row of data) {
    ;(row as any)._searchMatch = false
    ;(row as any)._searchActive = false
  }
}

function navigateSearch(direction: 'next' | 'prev') {
  if (searchMatches.value.length === 0) return
  let idx = searchCurrentMatch.value - 1
  if (direction === 'next') {
    idx = (idx + 1) % searchMatches.value.length
  } else {
    idx = (idx - 1 + searchMatches.value.length) % searchMatches.value.length
  }
  searchCurrentMatch.value = idx + 1

  const data = getCurrentSheetData()
  for (const row of data) {
    ;(row as any)._searchActive = false
  }
  const match = searchMatches.value[idx]
  ;(data[match.rowIndex] as any)._searchActive = true
}

function handleSearch(quer: string, options: SearchOptions) {
  doSearch(quer, options)
}

function handleNavigate(direction: 'next' | 'prev') {
  navigateSearch(direction)
}

function valueToSearchText(val: unknown): string {
  if (typeof val === 'string') {
    const trimmed = val.trim()
    if ((trimmed.startsWith('{') || trimmed.startsWith('[')) && (trimmed.endsWith('}') || trimmed.endsWith(']'))) {
      try {
        const parsed = JSON.parse(trimmed)
        return JSON.stringify(parsed, null, 2)
      } catch {
        // Not valid JSON, use as-is
      }
    }
    return val
  }
  if (val !== null && val !== undefined) {
    return JSON.stringify(val, null, 2)
  }
  return ''
}

function buildSearchPattern(query: string, options: SearchOptions): RegExp | null {
  try {
    const flags = options.matchCase ? 'g' : 'gi'
    const escaped = options.regex ? query : query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    const source = options.wholeWord ? `\\b${escaped}\\b` : escaped
    return new RegExp(source, flags)
  } catch {
    return null
  }
}

function handleReplace(replacement: string) {
  if (searchMatches.value.length === 0) return
  const idx = searchCurrentMatch.value - 1
  const match = searchMatches.value[idx]
  const data = getCurrentSheetData()
  const row = data[match.rowIndex]
  const oldVal = (row as any)[match.colKey]
  const pattern = buildSearchPattern(lastQuery.value, lastOptions.value)
  if (!pattern) return

  if (typeof oldVal === 'string') {
    (row as any)[match.colKey] = oldVal.replace(pattern, replacement)
    workbook.markModified?.()
  } else if (oldVal !== null && oldVal !== undefined && typeof oldVal === 'object') {
    // Replace within the JSON representation, then parse back
    const jsonStr = JSON.stringify(oldVal, null, 2)
    const newJsonStr = jsonStr.replace(pattern, replacement)
    try {
      (row as any)[match.colKey] = JSON.parse(newJsonStr)
      workbook.markModified?.()
    } catch {
      // If replacement produces invalid JSON, skip
    }
  }
  doSearch(lastQuery.value, lastOptions.value)
}

function handleReplaceAll(replacement: string) {
  const data = getCurrentSheetData()
  const pattern = buildSearchPattern(lastQuery.value, lastOptions.value)
  if (!pattern) return

  for (const match of searchMatches.value) {
    const row = data[match.rowIndex]
    const oldVal = (row as any)[match.colKey]
    if (typeof oldVal === 'string') {
      (row as any)[match.colKey] = oldVal.replace(pattern, replacement)
    } else if (oldVal !== null && oldVal !== undefined && typeof oldVal === 'object') {
      const jsonStr = JSON.stringify(oldVal, null, 2)
      const newJsonStr = jsonStr.replace(pattern, replacement)
      try {
        (row as any)[match.colKey] = JSON.parse(newJsonStr)
      } catch {
        // Skip if replacement produces invalid JSON
      }
    }
  }
  workbook.markModified?.()
  searchVisible.value = false
}

function closeSearch() {
  searchVisible.value = false
  searchReplaceMode.value = false
  clearSearchHighlights()
  searchMatches.value = []
  searchMatchCount.value = 0
  searchCurrentMatch.value = 0
}

// Re-run search when switching sheets
watch(() => editor.activeSheetIndex, () => {
  if (searchVisible.value) {
    closeSearch()
  }
})

// --- Global search state ---
const globalSearchVisible = ref(false)
const globalReplaceMode = ref(false)
const globalReplacementText = ref('')
const globalResults = ref<SearchResultItem[]>([])
const globalQuery = ref('')
const globalOptions = ref<SearchOptions>({ matchCase: false, wholeWord: false, regex: false })

interface SheetSource {
  name: string
  sheetIndex: number // -1=apiDef, 0=singleCase, 1+=bizFlow
  data: Record<string, unknown>[]
}

function getAllSheets(): SheetSource[] {
  const sheets: SheetSource[] = []
  sheets.push({
    name: t('table.sheetApiDef'),
    sheetIndex: -1,
    data: toRaw(workbook.apiDefinitions) as unknown as Record<string, unknown>[],
  })
  sheets.push({
    name: t('table.sheetSingleCase'),
    sheetIndex: 0,
    data: toRaw(workbook.singleCases) as unknown as Record<string, unknown>[],
  })
  workbook.bizFlows.forEach((flow, i) => {
    sheets.push({
      name: flow.sheetName || `BizFlow ${i + 1}`,
      sheetIndex: i + 1,
      data: toRaw(flow.steps) as unknown as Record<string, unknown>[],
    })
  })
  return sheets
}

function doGlobalSearch(query: string, options: SearchOptions) {
  globalQuery.value = query
  globalOptions.value = options

  let pattern: RegExp
  try {
    const flags = options.matchCase ? 'g' : 'gi'
    const escaped = options.regex ? query : query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    const source = options.wholeWord ? `\\b${escaped}\\b` : escaped
    pattern = new RegExp(source, flags)
  } catch {
    globalResults.value = []
    return
  }

  const results: SearchResultItem[] = []
  const sheets = getAllSheets()
  let groupIdx = 0

  for (const sheet of sheets) {
    const data = sheet.data
    for (let i = 0; i < data.length; i++) {
      const row = toRaw(data[i]) as Record<string, unknown>
      for (const [key, val] of Object.entries(row)) {
        if (key.startsWith('_')) continue
        const text = valueToSearchText(val)
        if (pattern.test(text)) {
          const displayText = text.length > 500 ? text.substring(0, 500) + '...' : text
          results.push({
            groupName: sheet.name,
            rowIndex: i,
            colKey: key,
            text: displayText,
            _groupIndex: groupIdx,
            _itemIndex: i,
          })
          pattern.lastIndex = 0
        }
      }
    }
    groupIdx++
  }

  globalResults.value = results
}

function handleGlobalNavigate(item: SearchResultItem) {
  // Find which sheet
  const sheets = getAllSheets()
  const sheet = sheets[item._groupIndex]
  if (!sheet) return

  // Switch to the correct sheet
  if (editor.activeSheetIndex !== sheet.sheetIndex) {
    editor.setActiveSheet(sheet.sheetIndex)
  }

  // After sheet switch, open local search and navigate to the row
  nextTick(() => {
    doSearch(globalQuery.value, globalOptions.value)
    // Find and activate the specific row
    if (searchMatches.value.length > 0) {
      const targetIdx = searchMatches.value.findIndex(
        m => m.rowIndex === item.rowIndex && m.colKey === item.colKey
      )
      if (targetIdx >= 0) {
        searchCurrentMatch.value = targetIdx + 1
        const data = getCurrentSheetData()
        for (const d of data) {
          ;(d as any)._searchActive = false
        }
        ;(data[item.rowIndex] as any)._searchActive = true
      }
    }
  })
}

function handleGlobalReplaceOne(item: SearchResultItem) {
  const sheets = getAllSheets()
  const sheet = sheets[item._groupIndex]
  if (!sheet) return

  const row = sheet.data[item.rowIndex]
  if (!row || !item.colKey) return

  const oldVal = (row as any)[item.colKey]
  const pattern = buildSearchPattern(globalQuery.value, globalOptions.value)
  if (!pattern) return

  if (typeof oldVal === 'string') {
    (row as any)[item.colKey] = oldVal.replace(pattern, globalReplacementText.value)
    workbook.markModified()
  } else if (oldVal !== null && oldVal !== undefined && typeof oldVal === 'object') {
    const jsonStr = JSON.stringify(oldVal, null, 2)
    const newJsonStr = jsonStr.replace(pattern, globalReplacementText.value)
    try {
      (row as any)[item.colKey] = JSON.parse(newJsonStr)
      workbook.markModified()
    } catch { /* skip */ }
  }

  // Re-run global search to update results
  doGlobalSearch(globalQuery.value, globalOptions.value)
}

function handleGlobalReplaceAll(replacement?: string) {
  const pattern = buildSearchPattern(globalQuery.value, globalOptions.value)
  if (!pattern) return
  const repl = replacement ?? globalReplacementText.value

  const sheets = getAllSheets()
  for (const sheet of sheets) {
    for (const row of sheet.data) {
      for (const [key, val] of Object.entries(row as Record<string, unknown>)) {
        if (key.startsWith('_')) continue
        if (typeof val === 'string') {
          const newVal = val.replace(pattern, repl)
          if (newVal !== val) {
            ;(row as any)[key] = newVal
          }
        } else if (val !== null && val !== undefined && typeof val === 'object') {
          const jsonStr = JSON.stringify(val, null, 2)
          const newJsonStr = jsonStr.replace(pattern, repl)
          if (newJsonStr !== jsonStr) {
            try {
              ;(row as any)[key] = JSON.parse(newJsonStr)
            } catch { /* skip */ }
          }
        }
      }
    }
  }
  workbook.markModified()
  globalSearchVisible.value = false
  globalResults.value = []
}

function closeGlobalSearch() {
  globalSearchVisible.value = false
  globalReplaceMode.value = false
  globalResults.value = []
  globalQuery.value = ''
}

// Watch for search action from AppHeader
watch(() => editor.searchAction, (action) => {
  if (!action) return
  switch (action.type) {
    case 'find':
      searchVisible.value = true
      searchReplaceMode.value = false
      break
    case 'replace':
      searchVisible.value = true
      searchReplaceMode.value = true
      break
    case 'findInFiles':
      globalSearchVisible.value = true
      globalReplaceMode.value = false
      globalResults.value = []
      break
    case 'replaceInFiles':
      globalSearchVisible.value = true
      globalReplaceMode.value = true
      globalResults.value = []
      break
  }
  editor.clearSearchAction()
})

// Keyboard shortcuts
function onKeyDown(e: KeyboardEvent) {
  if (e.ctrlKey && e.key === 'f') {
    e.preventDefault()
    searchVisible.value = true
    searchReplaceMode.value = false
  } else if (e.ctrlKey && e.key === 'h') {
    e.preventDefault()
    searchVisible.value = true
    searchReplaceMode.value = true
  } else if (e.key === 'Escape' && searchVisible.value) {
    e.preventDefault()
    closeSearch()
  }
}

onMounted(() => window.addEventListener('keydown', onKeyDown))
onUnmounted(() => window.removeEventListener('keydown', onKeyDown))
</script>

<template>
  <div style="height: 100%; display: flex; flex-direction: column; background: #f5f5f5;">
    <!-- Editor toolbar -->
    <div style="display: flex; justify-content: flex-end; border-bottom: 1px solid #f0f0f0">
      <EditorToolbar
        editor-type="excel"
        :file-path="workbookPath"
        @run-all="handleRunAll"
        @run-single="handleRunSingle"
        @run-biz="handleRunBiz"
        @run-select="handleRunSelect"
        @convert-all="handleConvertAll"
        @convert-single="handleConvertSingle"
        @convert-biz="handleConvertBiz"
        @convert-select="handleConvertSelect"
        @edit-run-params="handleEditRunParams"
        @edit-convert-params="handleEditConvertParams"
      />
    </div>

    <!-- Local search bar -->
    <SearchBar
      :visible="searchVisible && !globalSearchVisible"
      :replaceMode="searchReplaceMode"
      :matchCount="searchMatchCount"
      :currentMatch="searchCurrentMatch"
      @close="closeSearch"
      @update:replaceMode="searchReplaceMode = $event"
      @search="handleSearch"
      @navigate="handleNavigate"
      @replace="handleReplace"
      @replaceAll="handleReplaceAll"
    />

    <!-- Global search bar -->
    <div v-if="globalSearchVisible" style="display: flex; flex-direction: column; gap: 4px;">
      <SearchBar
        :visible="true"
        :replaceMode="globalReplaceMode"
        :matchCount="globalResults.length"
        :currentMatch="0"
        @close="closeGlobalSearch"
        @update:replaceMode="globalReplaceMode = $event"
        @search="(q, opts) => doGlobalSearch(q, opts)"
        @navigate="() => {}"
        @replace="(replacement: string) => { globalReplacementText = replacement; handleGlobalReplaceAll(replacement); }"
        @replaceAll="(replacement: string) => { globalReplacementText = replacement; handleGlobalReplaceAll(replacement); }"
      />
      <SearchResultsPanel
        :visible="globalResults.length > 0 || globalQuery.length > 0"
        :results="globalResults"
        :replaceMode="globalReplaceMode"
        :searchQuery="globalQuery"
        @close="closeGlobalSearch"
        @navigate="handleGlobalNavigate"
        @replaceOne="handleGlobalReplaceOne"
        @replaceAll="handleGlobalReplaceAll"
      />
    </div>

    <div style="flex: 1; min-height: 0;">
      <!-- API Definitions -->
      <ApiDefEditor v-if="editor.activeSheetIndex === -1" :search-bar-visible="searchVisible || globalSearchVisible" />

      <!-- Single Cases -->
      <SingleCaseEditor v-else-if="editor.activeSheetIndex === 0" :search-bar-visible="searchVisible || globalSearchVisible" />

      <!-- Biz Flow -->
      <BizFlowEditor
        v-else
        :flow-index="editor.activeSheetIndex - 1"
        :search-bar-visible="searchVisible || globalSearchVisible"
      />

      <!-- Empty state -->
      <div
        v-if="workbook.apiDefinitions.length === 0 && editor.activeSheetIndex === -1"
        style="display: flex; align-items: center; justify-content: center; height: 100%; color: #999;"
      >
        {{ t('table.noData') }}
      </div>
    </div>

    <!-- Log panel -->
    <LogPanel />

    <!-- Case select modal -->
    <CaseSelectModal
      v-model:visible="caseSelectVisible"
      :cases="caseSelectCases"
      @confirm="paramEditMode === 'converter' ? handleConvertCaseSelectConfirm($event) : handleCaseSelectConfirm($event)"
    />

    <!-- Param edit modal -->
    <ParamEditModal
      v-model:visible="paramEditVisible"
      :mode="paramEditMode"
      :file-path="workbookPath"
    />
  </div>
</template>
