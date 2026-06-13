<script setup lang="ts">
import { ref, watch, nextTick, computed } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

export interface SearchOptions {
  matchCase: boolean
  wholeWord: boolean
  regex: boolean
}

export interface SearchResult {
  rowIndex: number
  colKey: string
  text: string
}

export interface TextSearchResult {
  line: number
  column: number
  text: string
  start: number
  end: number
}

const props = defineProps<{
  visible: boolean
  replaceMode: boolean
  matchCount: number
  currentMatch: number
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'update:replaceMode', value: boolean): void
  (e: 'search', query: string, options: SearchOptions): void
  (e: 'navigate', direction: 'next' | 'prev'): void
  (e: 'replace', replacement: string): void
  (e: 'replaceAll', replacement: string): void
}>()

const query = ref('')
const replacement = ref('')
const matchCase = ref(false)
const wholeWord = ref(false)
const regex = ref(false)
const searchInput = ref<HTMLInputElement | null>(null)

const matchLabel = computed(() => {
  if (!query.value.trim()) return ''
  if (props.matchCount === 0) return t('search.noResults')
  return t('search.matchCount')
    .replace('{current}', String(props.currentMatch))
    .replace('{total}', String(props.matchCount))
})

let debounceTimer: ReturnType<typeof setTimeout> | null = null

function doSearch() {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    const q = query.value.trim()
    if (q) {
      emit('search', q, {
        matchCase: matchCase.value,
        wholeWord: wholeWord.value,
        regex: regex.value,
      })
    }
  }, 200)
}

watch(query, () => doSearch())
watch([matchCase, wholeWord, regex], () => {
  if (query.value.trim()) doSearch()
})

watch(() => props.visible, async (v) => {
  if (v) {
    await nextTick()
    searchInput.value?.focus()
  } else {
    query.value = ''
    replacement.value = ''
  }
})

function onKeyDown(e: KeyboardEvent) {
  if (e.key === 'Enter') {
    e.preventDefault()
    if (e.shiftKey) {
      emit('navigate', 'prev')
    } else {
      if (query.value.trim()) {
        emit('navigate', 'next')
      }
    }
  } else if (e.key === 'Escape') {
    e.preventDefault()
    emit('close')
  }
}

function onReplace() {
  if (replacement.value !== undefined) {
    emit('replace', replacement.value)
  }
}

function onReplaceAll() {
  if (replacement.value !== undefined) {
    emit('replaceAll', replacement.value)
  }
}
</script>

<template>
  <div v-if="visible" class="search-bar" @keydown="onKeyDown">
    <!-- Search row -->
    <div class="search-row">
      <button
        class="toggle-replace-btn"
        :title="replaceMode ? t('search.collapseReplace') : t('search.expandReplace')"
        @click="emit('update:replaceMode', !replaceMode)"
      >
        <svg viewBox="0 0 16 16" width="12" height="12">
          <path v-if="replaceMode" d="M8 11L3 6h10z" fill="currentColor"/>
          <path v-else d="M6 3l5 5H1z" fill="currentColor"/>
        </svg>
      </button>
      <input
        ref="searchInput"
        v-model="query"
        class="search-input"
        :placeholder="t('search.searchPlaceholder')"
        type="text"
      />
      <span class="match-label">{{ matchLabel }}</span>
      <button class="nav-btn" title="Shift+Enter" @click="emit('navigate', 'prev')">
        <svg viewBox="0 0 16 16" width="14" height="14"><path d="M8 12L3 7h10z" fill="currentColor"/></svg>
      </button>
      <button class="nav-btn" title="Enter" @click="emit('navigate', 'next')">
        <svg viewBox="0 0 16 16" width="14" height="14"><path d="M8 4l5 5H3z" fill="currentColor"/></svg>
      </button>
    </div>

    <!-- Replace row -->
    <div v-if="replaceMode" class="search-row">
      <textarea
        v-model="replacement"
        class="replace-textarea"
        :placeholder="t('search.replacePlaceholder')"
        rows="1"
      />
      <button class="action-btn" @click="onReplace">{{ t('search.replace') }}</button>
      <button class="action-btn" @click="onReplaceAll">{{ t('search.replaceAll') }}</button>
    </div>

    <!-- Options row -->
    <div class="options-row">
      <label class="option-label">
        <input type="checkbox" v-model="matchCase" />
        {{ t('search.matchCase') }}
      </label>
      <label class="option-label">
        <input type="checkbox" v-model="wholeWord" />
        {{ t('search.wholeWord') }}
      </label>
      <label class="option-label">
        <input type="checkbox" v-model="regex" />
        {{ t('search.regex') }}
      </label>
      <div style="flex: 1;"></div>
      <button class="close-btn" @click="emit('close')" title="Escape">
        <svg viewBox="0 0 16 16" width="14" height="14"><path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="2" fill="none"/></svg>
      </button>
    </div>
  </div>
</template>

<style scoped>
.search-bar {
  background: #2d2d2d;
  border: 1px solid #555;
  border-radius: 4px;
  padding: 4px 8px;
  display: flex;
  flex-direction: column;
  gap: 3px;
  font-size: 12px;
  color: #d4d4d4;
  user-select: none;
}

.search-row {
  display: flex;
  align-items: center;
  gap: 4px;
}

.search-input {
  flex: 1;
  min-width: 120px;
  background: #3c3c3c;
  border: 1px solid #555;
  border-radius: 3px;
  color: #d4d4d4;
  padding: 3px 6px;
  font-size: 12px;
  font-family: inherit;
  outline: none;
}

.search-input:focus {
  border-color: #4d90fe;
}

.replace-textarea {
  flex: 1;
  min-width: 120px;
  background: #3c3c3c;
  border: 1px solid #555;
  border-radius: 3px;
  color: #d4d4d4;
  padding: 3px 6px;
  font-size: 12px;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  outline: none;
  resize: vertical;
  min-height: 24px;
}

.replace-textarea:focus {
  border-color: #4d90fe;
}

.match-label {
  font-size: 11px;
  color: #999;
  white-space: nowrap;
  min-width: 80px;
  text-align: center;
}

.nav-btn, .action-btn, .close-btn {
  background: #3c3c3c;
  border: 1px solid #555;
  border-radius: 3px;
  color: #d4d4d4;
  cursor: pointer;
  padding: 2px 6px;
  font-size: 11px;
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 24px;
  height: 24px;
}

.nav-btn:hover, .action-btn:hover, .close-btn:hover {
  background: #4a4a4a;
}

.action-btn {
  padding: 2px 8px;
}

.options-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.option-label {
  display: flex;
  align-items: center;
  gap: 2px;
  font-size: 11px;
  color: #aaa;
  cursor: pointer;
}

.option-label input[type="checkbox"] {
  margin: 0;
  width: 12px;
  height: 12px;
}

.close-btn {
  min-width: 24px;
  padding: 2px;
}

.toggle-replace-btn {
  background: transparent;
  border: none;
  color: #999;
  cursor: pointer;
  padding: 2px;
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 24px;
  border-radius: 3px;
  flex-shrink: 0;
}

.toggle-replace-btn:hover {
  background: #4a4a4a;
  color: #d4d4d4;
}
</style>
