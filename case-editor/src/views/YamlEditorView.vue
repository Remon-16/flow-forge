<script setup lang="ts">
import { ref, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useYamlStore } from '../stores/yaml-store'
import { useEditorStore } from '../stores/editor'
import YamlFileTree from '../components/yaml-editor/YamlFileTree.vue'
import YamlTabBar from '../components/yaml-editor/YamlTabBar.vue'
import SingleCaseForm from '../components/yaml-editor/SingleCaseForm.vue'
import BizFlowForm from '../components/yaml-editor/BizFlowForm.vue'
import YamlRawView from '../components/yaml-editor/YamlRawView.vue'
import SearchBar from '../components/search/SearchBar.vue'
import SearchResultsPanel from '../components/search/SearchResultsPanel.vue'
import type { SearchResultItem } from '../components/search/SearchResultsPanel.vue'
import type { SearchOptions } from '../components/search/SearchBar.vue'
import { stringifyYaml, parseYaml } from '../utils/yaml-parser'

const { t } = useI18n()
const yamlStore = useYamlStore()
const editorStore = useEditorStore()
const rawViewRef = ref<InstanceType<typeof YamlRawView> | null>(null)

function onSelectFile(filePath: string) {
  yamlStore.openFile(filePath)
}

function onTabSwitch(index: number) {
  yamlStore.switchTab(index)
}

// Close confirm modal
const closeConfirmVisible = ref(false)
const closeConfirmIndex = ref(-1)

function onTabClose(index: number) {
  const tab = yamlStore.openTabs[index]
  if (tab && tab.modified) {
    closeConfirmIndex.value = index
    closeConfirmVisible.value = true
    yamlStore.switchTab(index)
  } else {
    yamlStore.closeTab(index)
  }
}

async function handleSaveAndClose() {
  await yamlStore.save()
  yamlStore.closeTab(closeConfirmIndex.value)
  closeConfirmVisible.value = false
}

function handleDiscardAndClose() {
  yamlStore.closeTab(closeConfirmIndex.value)
  closeConfirmVisible.value = false
}

function handleCancelClose() {
  closeConfirmVisible.value = false
}

// Search keyboard shortcuts
function onKeyDown(e: KeyboardEvent) {
  if (e.ctrlKey && e.key === 'f') {
    e.preventDefault()
    rawViewRef.value?.triggerSearch(false)
  } else if (e.ctrlKey && e.key === 'h') {
    e.preventDefault()
    rawViewRef.value?.triggerSearch(true)
  } else if (e.key === 'Escape' && rawViewRef.value?.isOpen) {
    // Let the search bar handle its own Escape first
  }
}

// --- Global search state ---
const globalSearchVisible = ref(false)
const globalReplaceMode = ref(false)
const globalResults = ref<SearchResultItem[]>([])
const globalQuery = ref('')
const globalOptions = ref<SearchOptions>({ matchCase: false, wholeWord: false, regex: false })

function buildSearchPattern(query: string, options: SearchOptions): RegExp | null {
  try {
    const flags = (options.matchCase ? 'g' : 'gi') + 'ms'
    const escaped = options.regex ? query : query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    const source = options.wholeWord ? `\\b${escaped}\\b` : escaped
    return new RegExp(source, flags)
  } catch {
    return null
  }
}

function doYamlGlobalSearch(query: string, options: SearchOptions) {
  globalQuery.value = query
  globalOptions.value = options

  const pattern = buildSearchPattern(query, options)
  if (!pattern) {
    globalResults.value = []
    return
  }

  const results: SearchResultItem[] = []
  const tabs = yamlStore.openTabs

  for (let tabIdx = 0; tabIdx < tabs.length; tabIdx++) {
    const tab = tabs[tabIdx]
    try {
      const text = stringifyYaml(tab.case)
      const lines = text.split('\n')
      // Pre-compute line starts for offset-to-line mapping
      const lineStarts: number[] = [0]
      for (let i = 0; i < lines.length; i++) {
        lineStarts.push(lineStarts[i] + lines[i].length + 1)
      }

      pattern.lastIndex = 0
      let match: RegExpExecArray | null
      while ((match = pattern.exec(text)) !== null) {
        const pos = match.index
        let lineNum = 1
        for (let l = 1; l < lineStarts.length; l++) {
          if (pos < lineStarts[l]) { lineNum = l; break }
        }
        // Show context: 1 line before and after the match
        const startLine = Math.max(0, lineNum - 2)
        const endLine = Math.min(lines.length - 1, lineNum)
        const contextLines: string[] = []
        for (let cl = startLine; cl <= endLine; cl++) {
          contextLines.push(lines[cl])
        }
        let displayText = contextLines.join('\n')
        if (displayText.length > 500) {
          displayText = displayText.substring(0, 500) + '...'
        }
        results.push({
          groupName: t('search.groupFile', { name: tab.title }),
          rowIndex: tabIdx,
          line: lineNum,
          text: displayText,
          _groupIndex: tabIdx,
          _itemIndex: match.index,
        })
        if (match[0].length === 0) pattern.lastIndex++
      }
    } catch {
      // Skip tabs that fail to serialize
    }
  }

  globalResults.value = results
}

function handleYamlGlobalNavigate(item: SearchResultItem) {
  // Switch to the correct tab
  const tabIdx = item._groupIndex
  if (tabIdx >= 0 && tabIdx < yamlStore.openTabs.length) {
    if (yamlStore.activeTabIndex !== tabIdx) {
      yamlStore.switchTab(tabIdx)
    }
  }

  // Open the raw view and navigate to the matching line
  nextTick(() => {
    rawViewRef.value?.triggerSearch(false)
    // Re-search and navigate
    if (item.line) {
      nextTick(() => {
        if (rawViewRef.value) {
          // We'll navigate by searching
          rawViewRef.value.triggerSearch(false)
        }
      })
    }
  })
}

function handleYamlGlobalReplaceOne(item: SearchResultItem) {
  const tabIdx = item._groupIndex
  if (tabIdx < 0 || tabIdx >= yamlStore.openTabs.length) return

  const tab = yamlStore.openTabs[tabIdx]
  try {
    const text = stringifyYaml(tab.case)
    const pattern = buildSearchPattern(globalQuery.value, globalOptions.value)
    if (!pattern) return

    // Replace the first occurrence matching the line position
    const lines = text.split('\n')
    const lineStarts: number[] = [0]
    for (let i = 0; i < lines.length; i++) {
      lineStarts.push(lineStarts[i] + lines[i].length + 1)
    }

    // Find the match at approximately the same position
    let replaced = false
    pattern.lastIndex = 0
    let match: RegExpExecArray | null
    while ((match = pattern.exec(text)) !== null) {
      const pos = match.index
      let lineNum = 1
      for (let l = 1; l < lineStarts.length; l++) {
        if (pos < lineStarts[l]) { lineNum = l; break }
      }
      if (lineNum === item.line) {
        const newText = text.substring(0, match.index) + '' + text.substring(match.index + match[0].length)
        try {
          const parsed = parseYaml(newText)
          if (parsed && parsed.case_type === tab.case.case_type) {
            tab.case = parsed
            tab.modified = true
            replaced = true
          }
        } catch { /* skip */ }
        break
      }
      if (match[0].length === 0) pattern.lastIndex++
    }

    if (replaced) {
      yamlStore.markModified()
      doYamlGlobalSearch(globalQuery.value, globalOptions.value)
    }
  } catch {
    // Skip tabs that fail
  }
}

function handleYamlGlobalReplaceAll() {
  const pattern = buildSearchPattern(globalQuery.value, globalOptions.value)
  if (!pattern) return

  for (const tab of yamlStore.openTabs) {
    try {
      const text = stringifyYaml(tab.case)
      const newText = text.replace(pattern, '')
      if (newText !== text) {
        try {
          const parsed = parseYaml(newText)
          if (parsed && parsed.case_type === tab.case.case_type) {
            tab.case = parsed
            tab.modified = true
          }
        } catch { /* skip */ }
      }
    } catch { /* skip */ }
  }
  yamlStore.markModified()
  globalSearchVisible.value = false
  globalResults.value = []
}

function closeYamlGlobalSearch() {
  globalSearchVisible.value = false
  globalReplaceMode.value = false
  globalResults.value = []
  globalQuery.value = ''
}

// Watch for search action from AppHeader
watch(() => editorStore.searchAction, (action) => {
  if (!action) return
  switch (action.type) {
    case 'find':
      rawViewRef.value?.triggerSearch(false)
      break
    case 'replace':
      rawViewRef.value?.triggerSearch(true)
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
  editorStore.clearSearchAction()
})

onMounted(() => window.addEventListener('keydown', onKeyDown))
onUnmounted(() => window.removeEventListener('keydown', onKeyDown))
</script>

<template>
  <div class="yaml-editor-view">
    <!-- Global search -->
    <div v-if="globalSearchVisible" class="yaml-global-search">
      <SearchBar
        :visible="true"
        :replaceMode="globalReplaceMode"
        :matchCount="globalResults.length"
        :currentMatch="0"
        @close="closeYamlGlobalSearch"
        @update:replaceMode="globalReplaceMode = $event"
        @search="(q: string, opts: SearchOptions) => doYamlGlobalSearch(q, opts)"
        @navigate="() => {}"
        @replace="() => {}"
        @replaceAll="() => {}"
      />
      <SearchResultsPanel
        :visible="globalResults.length > 0 || globalQuery.length > 0"
        :results="globalResults"
        :replaceMode="globalReplaceMode"
        :searchQuery="globalQuery"
        @close="closeYamlGlobalSearch"
        @navigate="handleYamlGlobalNavigate"
        @replaceOne="handleYamlGlobalReplaceOne"
        @replaceAll="handleYamlGlobalReplaceAll"
      />
    </div>

    <div class="yaml-body">
      <!-- Left: File tree -->
      <div class="yaml-left-panel">
        <YamlFileTree
          :files="yamlStore.fileTree"
          @select-file="onSelectFile"
        />
      </div>

      <!-- Center: Tab bar + Form editor -->
      <div class="yaml-center-panel">
        <!-- Tab bar -->
        <YamlTabBar
          :tabs="yamlStore.openTabs"
          :active-index="yamlStore.activeTabIndex"
          @switch="onTabSwitch"
          @close="onTabClose"
        />

        <div class="yaml-center-content">
          <div v-if="yamlStore.loading" class="yaml-loading">
            <a-spin size="large" :tip="t('loading')" />
          </div>

          <div v-else-if="!yamlStore.currentCase" class="yaml-empty">
            <div class="empty-icon">
              <svg viewBox="0 0 24 24" width="64" height="64" fill="none" stroke="#ccc" stroke-width="1">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
                <line x1="16" y1="13" x2="8" y2="13"/>
                <line x1="16" y1="17" x2="8" y2="17"/>
              </svg>
            </div>
            <p>{{ t('yaml.noFileSelected') }}</p>
            <p class="sub-hint">{{ t('yaml.selectFileHint') }}</p>
          </div>

          <!-- Single case form -->
          <SingleCaseForm v-else-if="yamlStore.isSingleCase" />

          <!-- Biz flow form -->
          <BizFlowForm v-else-if="yamlStore.isBizCase" />
        </div>
      </div>

      <!-- Right: Raw YAML view -->
      <YamlRawView ref="rawViewRef" />
    </div>

    <!-- Close confirm modal -->
    <a-modal
      v-model:open="closeConfirmVisible"
      :title="t('validator.unsavedTitle')"
      @cancel="handleCancelClose"
    >
      <p>{{ t('yaml.unsavedPrompt') }}</p>
      <template #footer>
        <a-button @click="handleCancelClose">{{ t('dialog.cancel') }}</a-button>
        <a-button @click="handleDiscardAndClose">{{ t('yaml.discardChanges') }}</a-button>
        <a-button type="primary" @click="handleSaveAndClose">{{ t('yaml.saveAndClose') }}</a-button>
      </template>
    </a-modal>
  </div>
</template>

<style scoped>
.yaml-editor-view {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.yaml-global-search {
  background: #1e1e1e;
  padding: 8px;
  border-bottom: 1px solid #333;
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex-shrink: 0;
}

.yaml-body {
  flex: 1;
  display: flex;
  overflow: hidden;
}

.yaml-left-panel {
  width: 250px;
  min-width: 180px;
  flex-shrink: 0;
}

.yaml-center-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
}

.yaml-center-content {
  flex: 1;
  overflow: auto;
}

.yaml-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}

.yaml-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #999;
  font-size: 16px;
  gap: 8px;
}

.sub-hint {
  font-size: 13px;
  color: #bbb;
}
</style>
