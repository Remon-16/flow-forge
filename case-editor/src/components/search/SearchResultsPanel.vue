<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

export interface SearchResultItem {
  groupName: string
  rowIndex: number
  colKey?: string
  line?: number
  text: string
  // For replace: which data array, index, and field
  _groupIndex: number
  _itemIndex: number
}

const { t } = useI18n()

const props = defineProps<{
  visible: boolean
  results: SearchResultItem[]
  replaceMode: boolean
  searchQuery: string
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'navigate', item: SearchResultItem): void
  (e: 'replaceOne', item: SearchResultItem): void
  (e: 'replaceAll'): void
}>()

const groupedResults = computed(() => {
  const groups: Record<string, SearchResultItem[]> = {}
  for (const item of props.results) {
    if (!groups[item.groupName]) {
      groups[item.groupName] = []
    }
    groups[item.groupName].push(item)
  }
  return groups
})

const groupState = ref<Record<string, boolean>>({})

function toggleGroup(name: string) {
  groupState.value[name] = !groupState.value[name]
}

function isGroupCollapsed(name: string): boolean {
  return groupState.value[name] !== false
}

import { ref } from 'vue'

const replacedSet = ref<Set<string>>(new Set())

function isReplaced(item: SearchResultItem): boolean {
  return replacedSet.value.has(`${item._groupIndex}_${item._itemIndex}`)
}

function handleReplaceOne(item: SearchResultItem) {
  replacedSet.value.add(`${item._groupIndex}_${item._itemIndex}`)
  emit('replaceOne', item)
}

function getLocationLabel(item: SearchResultItem): string {
  if (item.line !== undefined) {
    return `Line ${item.line}`
  }
  if (item.colKey) {
    return `Row ${item.rowIndex + 1}, ${item.colKey}`
  }
  return `Row ${item.rowIndex + 1}`
}
</script>

<template>
  <div v-if="visible" class="search-results-panel">
    <div class="results-toolbar">
      <span class="results-title">
        {{ t('search.globalResults') }}
        <span class="results-count">({{ results.length }})</span>
      </span>
      <div class="results-toolbar-actions">
        <button
          v-if="replaceMode"
          class="action-btn"
          :disabled="results.length === replacedSet.size"
          @click="emit('replaceAll')"
        >
          {{ t('search.replaceAll') }}
        </button>
        <button class="close-btn" @click="emit('close')" title="Escape">
          <svg viewBox="0 0 16 16" width="14" height="14"><path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="2" fill="none"/></svg>
        </button>
      </div>
    </div>

    <div class="results-body">
      <div v-if="results.length === 0" class="no-results">
        {{ t('search.noResults') }}
      </div>

      <div
        v-for="(items, groupName) in groupedResults"
        :key="groupName"
        class="result-group"
      >
        <div class="group-header" @click="toggleGroup(groupName)">
          <svg
            viewBox="0 0 16 16"
            width="10"
            height="10"
            :class="{ rotated: !isGroupCollapsed(groupName) }"
          >
            <path d="M6 3l5 5H1z" fill="currentColor"/>
          </svg>
          <span class="group-name">{{ groupName }}</span>
          <span class="group-count">({{ items.length }})</span>
        </div>

        <div v-if="!isGroupCollapsed(groupName)" class="group-items">
          <div
            v-for="item in items"
            :key="`${item._groupIndex}_${item._itemIndex}`"
            class="result-item"
            :class="{ replaced: isReplaced(item) }"
            @click="emit('navigate', item)"
          >
            <div class="result-location">{{ getLocationLabel(item) }}</div>
            <div class="result-text">{{ item.text }}</div>
            <button
              v-if="replaceMode && !isReplaced(item)"
              class="replace-one-btn"
              @click.stop="handleReplaceOne(item)"
            >
              {{ t('search.replaceOne') }}
            </button>
            <span v-else-if="replaceMode && isReplaced(item)" class="replaced-label">
              {{ t('search.replaced') }}
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.search-results-panel {
  background: #2d2d2d;
  border: 1px solid #555;
  border-radius: 4px;
  display: flex;
  flex-direction: column;
  max-height: 400px;
  font-size: 12px;
  color: #d4d4d4;
}

.results-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 8px;
  border-bottom: 1px solid #444;
  flex-shrink: 0;
}

.results-title {
  font-weight: 600;
  font-size: 12px;
}

.results-count {
  color: #999;
  font-weight: 400;
}

.results-toolbar-actions {
  display: flex;
  gap: 4px;
  align-items: center;
}

.action-btn, .close-btn {
  background: #3c3c3c;
  border: 1px solid #555;
  border-radius: 3px;
  color: #d4d4d4;
  cursor: pointer;
  padding: 2px 8px;
  font-size: 11px;
  display: flex;
  align-items: center;
  justify-content: center;
  height: 24px;
}

.action-btn:hover, .close-btn:hover {
  background: #4a4a4a;
}

.action-btn:disabled {
  opacity: 0.4;
  cursor: default;
}

.results-body {
  overflow-y: auto;
  flex: 1;
}

.no-results {
  padding: 16px;
  text-align: center;
  color: #999;
}

.result-group {
  border-bottom: 1px solid #3a3a3a;
}

.group-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  cursor: pointer;
  background: #333;
  user-select: none;
  font-size: 11px;
}

.group-header:hover {
  background: #3a3a3a;
}

.group-header svg {
  transition: transform 0.15s;
  color: #999;
  flex-shrink: 0;
}

.group-header svg.rotated {
  transform: rotate(90deg);
}

.group-name {
  font-weight: 600;
}

.group-count {
  color: #999;
}

.result-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 3px 8px 3px 24px;
  cursor: pointer;
  border-left: 3px solid transparent;
}

.result-item:hover {
  background: #3a3a3a;
}

.result-item.replaced {
  opacity: 0.5;
}

.result-location {
  color: #6a9;
  white-space: nowrap;
  font-size: 11px;
  min-width: 100px;
}

.result-text {
  flex: 1;
  white-space: pre-wrap;
  max-height: 120px;
  overflow-y: auto;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 11px;
  line-height: 1.5;
}

.replace-one-btn {
  background: #3c3c3c;
  border: 1px solid #555;
  border-radius: 3px;
  color: #d4d4d4;
  cursor: pointer;
  padding: 1px 6px;
  font-size: 10px;
  white-space: nowrap;
  flex-shrink: 0;
}

.replace-one-btn:hover {
  background: #4a4a4a;
}

.replaced-label {
  color: #999;
  font-size: 10px;
  white-space: nowrap;
  flex-shrink: 0;
}
</style>
