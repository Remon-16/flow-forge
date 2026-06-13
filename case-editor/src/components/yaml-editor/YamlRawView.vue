<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { useYamlStore } from '../../stores/yaml-store'
import { stringifyYaml, parseYaml } from '../../utils/yaml-parser'
import SearchBar from '../search/SearchBar.vue'
import type { SearchOptions } from '../search/SearchBar.vue'

const { t } = useI18n()
const yamlStore = useYamlStore()

const isOpen = ref(false)
const editMode = ref(true)
const editText = ref('')
const textareaRef = ref<{ $el?: HTMLTextAreaElement; resizableTextArea?: { textArea: HTMLTextAreaElement } } | null>(null)

let debounceTimer: ReturnType<typeof setTimeout> | null = null
let suppressSync = false

const yamlText = computed(() => {
  if (!yamlStore.currentCase) return ''
  try {
    return stringifyYaml(yamlStore.currentCase)
  } catch (err) {
    console.error('Failed to stringify YAML:', err)
    return '# Error: Failed to generate YAML'
  }
})

watch(
  () => yamlStore.currentCase,
  () => {
    if (editMode.value) {
      suppressSync = true
      editText.value = yamlText.value
    }
  },
  { immediate: true }
)

watch(editText, (newText) => {
  if (suppressSync) {
    suppressSync = false
    return
  }
  if (!editMode.value) return
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    try {
      const parsed = parseYaml(newText)
      if (parsed && parsed.case_type === yamlStore.currentCase?.case_type) {
        yamlStore.currentCase = parsed
        yamlStore.markModified()
      }
    } catch {
      // Ignore parse errors during typing
    }
  }, 500)
})

function togglePanel() {
  isOpen.value = !isOpen.value
  if (isOpen.value) {
    editText.value = yamlText.value
    editMode.value = true
  }
}

function toggleEditMode() {
  if (editMode.value) {
    editMode.value = false
  } else {
    editText.value = yamlText.value
    editMode.value = true
  }
}

function onTextBlur() {
  if (!editMode.value) return
  if (debounceTimer) {
    clearTimeout(debounceTimer)
    debounceTimer = null
  }
  try {
    const parsed = parseYaml(editText.value)
    if (parsed && parsed.case_type === yamlStore.currentCase?.case_type) {
      yamlStore.currentCase = parsed
      yamlStore.markModified()
    }
  } catch {
    // Ignore parse errors on blur
  }
}

// --- Search ---
const searchVisible = ref(false)
const searchReplaceMode = ref(false)
const searchMatchCount = ref(0)
const searchCurrentMatch = ref(1)
const searchMatchResults = ref<Array<{ line: number; text: string; start: number; end: number }>>([])
const searchQuery = ref('')

function getTextArea(): HTMLTextAreaElement | null {
  if (!textareaRef.value) return null
  const el = textareaRef.value as any
  return el?.resizableTextArea?.textArea || el?.$el?.querySelector?.('textarea') || el?.$el || null
}

function doYamlSearch(query: string, options: SearchOptions) {
  searchQuery.value = query
  const text = editMode.value ? editText.value : yamlText.value
  const lines = text.split('\n')
  const results: Array<{ line: number; text: string; start: number; end: number }> = []

  let pattern: RegExp
  try {
    const flags = options.matchCase ? 'g' : 'gi'
    const escaped = options.regex ? query : query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    const source = options.wholeWord ? `\\b${escaped}\\b` : escaped
    pattern = new RegExp(source, flags)
  } catch {
    searchMatchCount.value = 0
    searchCurrentMatch.value = 0
    searchMatchResults.value = []
    return
  }

  let globalOffset = 0
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    pattern.lastIndex = 0
    let match: RegExpExecArray | null
    while ((match = pattern.exec(line)) !== null) {
      results.push({
        line: i + 1,
        text: line.trim(),
        start: globalOffset + match.index,
        end: globalOffset + match.index + match[0].length,
      })
      if (match[0].length === 0) pattern.lastIndex++
    }
    globalOffset += line.length + 1
  }

  searchMatchResults.value = results
  searchMatchCount.value = results.length
  searchCurrentMatch.value = results.length > 0 ? 1 : 0
}

function navigateYamlSearch(direction: 'next' | 'prev') {
  if (searchMatchResults.value.length === 0) return
  let idx = searchCurrentMatch.value - 1
  if (direction === 'next') {
    idx = (idx + 1) % searchMatchResults.value.length
  } else {
    idx = (idx - 1 + searchMatchResults.value.length) % searchMatchResults.value.length
  }
  searchCurrentMatch.value = idx + 1

  const match = searchMatchResults.value[idx]
  const ta = getTextArea()
  if (ta) {
    ta.focus()
    ta.setSelectionRange(match.start, match.end)
    // Scroll to make the selection visible
    const lineHeight = 18
    const targetScroll = Math.max(0, match.line * lineHeight - 100)
    ta.scrollTop = targetScroll
  }
}

function handleYamlReplace(replacement: string) {
  if (searchMatchResults.value.length === 0) return
  const idx = searchCurrentMatch.value - 1
  const match = searchMatchResults.value[idx]
  const before = editText.value.substring(0, match.start)
  const after = editText.value.substring(match.end)
  editText.value = before + replacement + after

  // Re-search
  if (searchQuery.value) {
    doYamlSearch(searchQuery.value, { matchCase: false, wholeWord: false, regex: false })
  }
}

function handleYamlReplaceAll(replacement: string) {
  // Replace all matches in reverse order to preserve positions
  const sorted = [...searchMatchResults.value].sort((a, b) => b.start - a.start)
  let text = editText.value
  for (const match of sorted) {
    text = text.substring(0, match.start) + replacement + text.substring(match.end)
  }
  editText.value = text
  searchVisible.value = false
  searchMatchResults.value = []
  searchMatchCount.value = 0
  searchCurrentMatch.value = 0
}

function closeYamlSearch() {
  searchVisible.value = false
  searchReplaceMode.value = false
  searchMatchResults.value = []
  searchMatchCount.value = 0
  searchCurrentMatch.value = 0
  searchQuery.value = ''
}

function triggerSearch(replaceMode = false) {
  isOpen.value = true
  editMode.value = true
  searchVisible.value = true
  searchReplaceMode.value = replaceMode
  editText.value = yamlText.value
  nextTick(() => {
    const ta = getTextArea()
    if (ta) ta.focus()
  })
}

defineExpose({ triggerSearch, isOpen })
</script>

<template>
  <div class="yaml-raw-view" :class="{ open: isOpen }">
    <div class="raw-toggle" @click="togglePanel" :title="t('yaml.rawView')">
      <span class="toggle-label">
        <span v-if="!isOpen" class="toggle-hint">YAML</span>
        <span v-else>{{ t('yaml.rawView') }}</span>
        <span class="toggle-arrow">{{ isOpen ? '▶' : '◀' }}</span>
      </span>
    </div>

    <div v-if="isOpen" class="raw-content">
      <div class="raw-toolbar">
        <span class="raw-title">{{ t('yaml.rawView') }}</span>
        <a-button size="small" type="text" @click="toggleEditMode">
          {{ editMode ? t('yaml.formView') : t('yaml.splitView') }}
        </a-button>
      </div>

      <!-- Search bar -->
      <SearchBar
        :visible="searchVisible"
        :replaceMode="searchReplaceMode"
        :matchCount="searchMatchCount"
        :currentMatch="searchCurrentMatch"
        @close="closeYamlSearch"
        @update:replaceMode="searchReplaceMode = $event"
        @search="(q, opts: SearchOptions) => doYamlSearch(q, opts)"
        @navigate="navigateYamlSearch"
        @replace="handleYamlReplace"
        @replaceAll="handleYamlReplaceAll"
      />

      <!-- Editable textarea (default) -->
      <a-textarea
        v-if="editMode"
        ref="textareaRef"
        v-model:value="editText"
        class="raw-editor"
        :auto-size="false"
        @blur="onTextBlur"
      />

      <!-- Read-only preview -->
      <pre v-else class="raw-preview">{{ yamlText }}</pre>
    </div>
  </div>
</template>

<style scoped>
.yaml-raw-view {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #1e1e1e;
  color: #d4d4d4;
  border-left: 1px solid #333;
  transition: width 0.2s;
  width: 40px;
  min-width: 40px;
  overflow: hidden;
}

.yaml-raw-view.open {
  width: 320px;
  min-width: 200px;
}

.raw-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 8px 4px;
  cursor: pointer;
  user-select: none;
  writing-mode: vertical-rl;
  text-orientation: mixed;
  flex-shrink: 0;
}

.yaml-raw-view.open .raw-toggle {
  writing-mode: horizontal-tb;
  justify-content: flex-start;
}

.toggle-label {
  font-size: 12px;
  color: #999;
}

.toggle-hint {
  font-size: 11px;
  letter-spacing: 2px;
}

.toggle-arrow {
  font-size: 10px;
}

.raw-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.raw-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 8px;
  border-bottom: 1px solid #333;
}

.raw-title {
  font-size: 12px;
  font-weight: 600;
  color: #999;
}

.raw-preview {
  flex: 1;
  margin: 0;
  padding: 12px;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.5;
  overflow: auto;
  white-space: pre;
  color: #d4d4d4;
}

.raw-editor {
  flex: 1;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace !important;
  font-size: 12px !important;
  line-height: 1.5;
  background: #1e1e1e;
  color: #d4d4d4;
  border: none;
  resize: none;
}

.raw-editor :deep(textarea) {
  background: #1e1e1e !important;
  color: #d4d4d4 !important;
  border: none !important;
  height: 100% !important;
}
</style>
