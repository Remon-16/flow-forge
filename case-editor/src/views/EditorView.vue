<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { toRaw } from 'vue'
import { useEditorStore } from '../stores/editor'
import { useWorkbookStore } from '../stores/workbook'
import { useI18n } from 'vue-i18n'
import ApiDefEditor from '../components/editor/ApiDefEditor.vue'
import SingleCaseEditor from '../components/editor/SingleCaseEditor.vue'
import BizFlowEditor from '../components/editor/BizFlowEditor.vue'
import SearchBar from '../components/search/SearchBar.vue'
import SearchResultsPanel from '../components/search/SearchResultsPanel.vue'
import type { SearchResultItem } from '../components/search/SearchResultsPanel.vue'
import type { SearchOptions } from '../components/search/SearchBar.vue'

const { t } = useI18n()
const editor = useEditorStore()
const workbook = useWorkbookStore()

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
      const text = typeof val === 'string'
        ? val
        : val !== null && val !== undefined
          ? JSON.stringify(val, null, 2)
          : ''
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
        const text = typeof val === 'string'
          ? val
          : val !== null && val !== undefined
            ? JSON.stringify(val, null, 2)
            : ''
        if (pattern.test(text)) {
          const displayText = text.length > 80 ? text.substring(0, 80) + '...' : text
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
    (row as any)[item.colKey] = oldVal.replace(pattern, '')
    workbook.markModified()
  } else if (oldVal !== null && oldVal !== undefined && typeof oldVal === 'object') {
    const jsonStr = JSON.stringify(oldVal, null, 2)
    const newJsonStr = jsonStr.replace(pattern, '')
    try {
      (row as any)[item.colKey] = JSON.parse(newJsonStr)
      workbook.markModified()
    } catch { /* skip */ }
  }

  // Re-run global search to update results
  doGlobalSearch(globalQuery.value, globalOptions.value)
}

function handleGlobalReplaceAll() {
  const pattern = buildSearchPattern(globalQuery.value, globalOptions.value)
  if (!pattern) return

  const sheets = getAllSheets()
  for (const sheet of sheets) {
    for (const row of sheet.data) {
      for (const [key, val] of Object.entries(row as Record<string, unknown>)) {
        if (key.startsWith('_')) continue
        if (typeof val === 'string') {
          const newVal = val.replace(pattern, '')
          if (newVal !== val) {
            ;(row as any)[key] = newVal
          }
        } else if (val !== null && val !== undefined && typeof val === 'object') {
          const jsonStr = JSON.stringify(val, null, 2)
          const newJsonStr = jsonStr.replace(pattern, '')
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
  <div style="height: 100%; display: flex; flex-direction: column;">
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
        :replaceMode="false"
        :matchCount="globalResults.length"
        :currentMatch="0"
        @close="closeGlobalSearch"
        @search="(q, opts) => doGlobalSearch(q, opts)"
        @navigate="() => {}"
        @replace="() => {}"
        @replaceAll="() => {}"
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

    <!-- API Definitions -->
    <ApiDefEditor v-if="editor.activeSheetIndex === -1" />

    <!-- Single Cases -->
    <SingleCaseEditor v-else-if="editor.activeSheetIndex === 0" />

    <!-- Biz Flow -->
    <BizFlowEditor
      v-else
      :flow-index="editor.activeSheetIndex - 1"
    />

    <!-- Empty state -->
    <div
      v-if="workbook.apiDefinitions.length === 0 && editor.activeSheetIndex === -1"
      style="display: flex; align-items: center; justify-content: center; height: 100%; color: #999;"
    >
      {{ t('table.noData') }}
    </div>
  </div>
</template>
