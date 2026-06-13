<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { useEditorStore } from '../stores/editor'
import { useWorkbookStore } from '../stores/workbook'
import { useI18n } from 'vue-i18n'
import ApiDefEditor from '../components/editor/ApiDefEditor.vue'
import SingleCaseEditor from '../components/editor/SingleCaseEditor.vue'
import BizFlowEditor from '../components/editor/BizFlowEditor.vue'
import SearchBar from '../components/search/SearchBar.vue'
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
  const data = getCurrentSheetData()
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
    const row = data[i]
    for (const [key, val] of Object.entries(row)) {
      if (key.startsWith('_')) continue
      const text = typeof val === 'string' ? val : val !== null && val !== undefined ? JSON.stringify(val) : ''
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

function handleReplace(replacement: string) {
  if (searchMatches.value.length === 0) return
  const idx = searchCurrentMatch.value - 1
  const match = searchMatches.value[idx]
  const data = getCurrentSheetData()
  const row = data[match.rowIndex]
  const oldVal = (row as any)[match.colKey]
  if (typeof oldVal === 'string') {
    (row as any)[match.colKey] = oldVal.replace(
      new RegExp(oldVal, 'gi'),
      replacement,
    )
    workbook.markModified?.()
  }
  doSearch(lastQuery.value, lastOptions.value)
}

function handleReplaceAll(replacement: string) {
  const data = getCurrentSheetData()
  for (const match of searchMatches.value) {
    const row = data[match.rowIndex]
    const oldVal = (row as any)[match.colKey]
    if (typeof oldVal === 'string') {
      (row as any)[match.colKey] = oldVal.replace(/.*/, replacement)
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
    <!-- Search bar -->
    <SearchBar
      :visible="searchVisible"
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
