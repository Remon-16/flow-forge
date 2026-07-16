<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { useYamlStore } from '../stores/yaml-store'
import { useEditorStore } from '../stores/editor'
import { useExecutorStore } from '../stores/executor'
import { useConverterStore } from '../stores/converter'
import { useAgentStore } from '../stores/agent'
import YamlFileTree from '../components/yaml-editor/YamlFileTree.vue'
import YamlTabBar from '../components/yaml-editor/YamlTabBar.vue'
import SingleCaseForm from '../components/yaml-editor/SingleCaseForm.vue'
import BizFlowForm from '../components/yaml-editor/BizFlowForm.vue'
import InterfaceForm from '../components/yaml-editor/InterfaceForm.vue'
import YamlRawView from '../components/yaml-editor/YamlRawView.vue'
import SearchBar from '../components/search/SearchBar.vue'
import SearchResultsPanel from '../components/search/SearchResultsPanel.vue'
import EditorToolbar from '../components/editor/EditorToolbar.vue'
import LogPanel from '../components/editor/LogPanel.vue'
import ParamEditModal from '../components/editor/ParamEditModal.vue'
import type { SearchResultItem } from '../components/search/SearchResultsPanel.vue'
import type { SearchOptions } from '../components/search/SearchBar.vue'
import { stringifyYaml, parseYaml } from '../utils/yaml-parser'
import { readFile, writeFile } from '../utils/desktop-bridge'
import type { FileEntry } from '../utils/desktop-bridge'

const { t } = useI18n()
const yamlStore = useYamlStore()
const editorStore = useEditorStore()
const executor = useExecutorStore()
const converter = useConverterStore()
const agent = useAgentStore()

// ============================================================================
// Editor toolbar state / 编辑器工具栏状态
// ============================================================================

const paramEditVisible = ref(false)
const paramEditMode = ref<'executor' | 'converter'>('executor')

// 当前激活文件的路径 / Current active file path
const currentFilePath = computed(() => {
  const tab = yamlStore.openTabs[yamlStore.activeTabIndex]
  return tab?.filePath || ''
})

// 当前激活文件的目录 / Current active file directory
const currentDir = computed(() => {
  const tab = yamlStore.openTabs[yamlStore.activeTabIndex]
  return tab?.filePath ? tab.filePath.replace(/[/\\][^/\\]+$/, '') : ''
})

// ============================================================================
// Toolbar handlers for YAML editor
// ============================================================================

async function handleRunAll() {
  try {
    const fp = currentFilePath.value
    if (!fp) { message.warning(t('yaml.noFileSelected')); return }
    const sessionId = executor.createSession({
      envSuffix: '',
      caseFilePath: '',
      yamlDir: '',
      yamlFiles: fp,
      envOnlyParams: {},
      cliParams: executor.getEditorCliParams(fp),
    })
    await executor.startSession(sessionId)
  } catch (e: unknown) { message.error(String(e)) }
}

async function handleRunSingle() {
  try {
    const fp = currentFilePath.value
    if (!fp) { message.warning(t('yaml.noFileSelected')); return }
    const sessionId = executor.createSession({
      envSuffix: '',
      caseFilePath: '',
      yamlDir: '',
      yamlFiles: fp,
      envOnlyParams: {},
      cliParams: { ...executor.getEditorCliParams(fp), apiMode: 'single' },
    })
    await executor.startSession(sessionId)
  } catch (e: unknown) { message.error(String(e)) }
}

async function handleRunBiz() {
  try {
    const fp = currentFilePath.value
    if (!fp) { message.warning(t('yaml.noFileSelected')); return }
    const sessionId = executor.createSession({
      envSuffix: '',
      caseFilePath: '',
      yamlDir: '',
      yamlFiles: fp,
      envOnlyParams: {},
      cliParams: { ...executor.getEditorCliParams(fp), apiMode: 'biz' },
    })
    await executor.startSession(sessionId)
  } catch (e: unknown) { message.error(String(e)) }
}

async function handleRunSelect() {
  // YAML: use current directory for selection
  await handleRunAll()
}

async function handleConvertAll() {
  try {
    const dir = currentDir.value
    if (!dir) { message.warning(t('yaml.noFileSelected')); return }
    const sessionId = converter.createSession({
      direction: 'yaml2excel',
      inputPath: '',
      outputPath: dir + '/_converted.xlsx',
      interfacesDir: dir,
      singleCasesDir: dir,
      bizFlowsDir: dir,
      configDir: '',
      processorsDir: '',
    })
    await converter.startSession(sessionId)
  } catch (e: unknown) { message.error(String(e)) }
}

async function handleConvertSingle() {
  await handleConvertAll()
}

async function handleConvertBiz() {
  await handleConvertAll()
}

async function handleConvertSelect() {
  await handleConvertAll()
}

function handleEditRunParams() {
  paramEditMode.value = 'executor'
  paramEditVisible.value = true
}

function handleEditConvertParams() {
  paramEditMode.value = 'converter'
  paramEditVisible.value = true
}
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
const globalReplacementText = ref('')
const globalCurrentResult = ref(0)

function handleGlobalNavigate(direction: 'next' | 'prev') {
  if (globalResults.value.length === 0) return
  if (direction === 'next') {
    globalCurrentResult.value = (globalCurrentResult.value + 1) % globalResults.value.length
  } else {
    globalCurrentResult.value = (globalCurrentResult.value - 1 + globalResults.value.length) % globalResults.value.length
  }
  const item = globalResults.value[globalCurrentResult.value]
  handleYamlGlobalNavigate(item)
}

function collectYamlPaths(entries: FileEntry[]): string[] {
  const paths: string[] = []
  for (const entry of entries) {
    if (!entry.isDirectory) {
      paths.push(entry.path)
    } else if (entry.children) {
      paths.push(...collectYamlPaths(entry.children))
    }
  }
  return paths
}

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

async function doYamlGlobalSearch(query: string, options: SearchOptions) {
  globalQuery.value = query
  globalOptions.value = options

  const pattern = buildSearchPattern(query, options)
  if (!pattern) {
    globalResults.value = []
    return
  }

  const results: SearchResultItem[] = []
  const searchedPaths = new Set<string>()

  // Helper to search text from a file and add results
  function searchText(filePath: string, fileName: string, text: string, fileIdx: number, pat: RegExp) {
    try {
      const lines = text.split('\n')
      const lineStarts: number[] = [0]
      for (let i = 0; i < lines.length; i++) {
        lineStarts.push(lineStarts[i] + lines[i].length + 1)
      }

      pat.lastIndex = 0
      let match: RegExpExecArray | null
      while ((match = pat.exec(text)) !== null) {
        const pos = match.index
        let lineNum = 1
        for (let l = 1; l < lineStarts.length; l++) {
          if (pos < lineStarts[l]) { lineNum = l; break }
        }
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
          groupName: fileName,
          rowIndex: fileIdx,
          line: lineNum,
          text: displayText,
          _groupIndex: fileIdx,
          _itemIndex: match.index,
          _filePath: filePath,
        })
        if (match[0].length === 0) pat.lastIndex++
      }
    } catch (err) {
      console.error('YAML global search failed for file:', fileName, err)
    }
  }

  // 1. Search all open tabs first (uses in-memory state)
  for (let tabIdx = 0; tabIdx < yamlStore.openTabs.length; tabIdx++) {
    const tab = yamlStore.openTabs[tabIdx]
    const filePath = tab.path
    if (!filePath || searchedPaths.has(filePath)) continue
    searchedPaths.add(filePath)
    const fileName = filePath.split(/[/\\]/).pop() || filePath
    const text = stringifyYaml(tab.case)
    searchText(filePath, fileName, text, tabIdx, pattern!)
  }

  // 2. Search fileTree files not already covered by open tabs
  const allPaths = collectYamlPaths(yamlStore.fileTree)

  for (const filePath of allPaths) {
    if (searchedPaths.has(filePath)) continue
    searchedPaths.add(filePath)
    const fileName = filePath.split(/[/\\]/).pop() || filePath

    let text: string
    try {
      text = await readFile(filePath)
      text = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
    } catch {
      continue
    }

    searchText(filePath, fileName, text, results.length, pattern!)
  }

  globalResults.value = results
}

async function handleYamlGlobalNavigate(item: SearchResultItem) {
  const filePath = item._filePath
  if (!filePath) return

  const existingIdx = yamlStore.openTabs.findIndex(t => t.path === filePath)
  if (existingIdx >= 0) {
    if (yamlStore.activeTabIndex !== existingIdx) {
      yamlStore.switchTab(existingIdx)
    }
  } else {
    await yamlStore.openFile(filePath)
  }
}

async function handleYamlGlobalReplaceOne(item: SearchResultItem) {
  const filePath = item._filePath
  if (!filePath) return

  const pattern = buildSearchPattern(globalQuery.value, globalOptions.value)
  if (!pattern) return

  const existingTab = yamlStore.openTabs.find(t => t.path === filePath)

  let text: string
  if (existingTab) {
    text = stringifyYaml(existingTab.case)
  } else {
    try {
      text = await readFile(filePath)
      text = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
    } catch {
      return
    }
  }

  const lines = text.split('\n')
  const lineStarts: number[] = [0]
  for (let i = 0; i < lines.length; i++) {
    lineStarts.push(lineStarts[i] + lines[i].length + 1)
  }

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
      const newText = text.substring(0, match.index) + globalReplacementText.value + text.substring(match.index + match[0].length)
      if (existingTab) {
        try {
          const parsed = parseYaml(newText)
          if (parsed && parsed.case_type === existingTab.case.case_type) {
            existingTab.case = parsed
            existingTab.modified = true
            replaced = true
          }
        } catch { /* skip */ }
      } else {
        try {
          await writeFile(filePath, newText)
          replaced = true
        } catch { /* skip */ }
      }
      break
    }
    if (match[0].length === 0) pattern.lastIndex++
  }

  if (replaced) {
    if (existingTab) yamlStore.markModified()
    await doYamlGlobalSearch(globalQuery.value, globalOptions.value)
  }
}

async function handleYamlGlobalReplaceAll(replacement?: string) {
  const pattern = buildSearchPattern(globalQuery.value, globalOptions.value)
  if (!pattern) return
  const repl = replacement ?? globalReplacementText.value

  const processedPaths = new Set<string>()

  // Process open tabs (in-memory state via stringifyYaml)
  for (const tab of yamlStore.openTabs) {
    const filePath = tab.path
    if (!filePath || processedPaths.has(filePath)) continue
    processedPaths.add(filePath)

    try {
      const text = stringifyYaml(tab.case)
      const newText = text.replace(pattern, repl)
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

  // Process fileTree files not already covered by open tabs
  const allPaths = collectYamlPaths(yamlStore.fileTree)
  for (const filePath of allPaths) {
    if (processedPaths.has(filePath)) continue
    processedPaths.add(filePath)

    let text: string
    try {
      text = await readFile(filePath)
      text = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
    } catch {
      continue
    }

    try {
      const newText = text.replace(pattern, repl)
      if (newText !== text) {
        try {
          await writeFile(filePath, newText)
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
    <!-- Editor toolbar -->
    <div style="display: flex; justify-content: flex-end; border-bottom: 1px solid #f0f0f0; background: #fff;">
      <EditorToolbar
        editor-type="yaml"
        :file-path="currentFilePath"
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

    <!-- Global search -->
    <div v-if="globalSearchVisible" class="yaml-global-search">
      <SearchBar
        :visible="true"
        :replaceMode="globalReplaceMode"
        :matchCount="globalResults.length"
        :currentMatch="globalResults.length > 0 ? globalCurrentResult + 1 : 0"
        @close="closeYamlGlobalSearch"
        @update:replaceMode="globalReplaceMode = $event"
        @search="(q: string, opts: SearchOptions) => { globalCurrentResult = 0; doYamlGlobalSearch(q, opts); }"
        @navigate="(direction: 'next' | 'prev') => handleGlobalNavigate(direction)"
        @replace="(replacement: string) => { globalReplacementText = replacement; handleYamlGlobalReplaceAll(replacement); }"
        @replaceAll="(replacement: string) => { globalReplacementText = replacement; handleYamlGlobalReplaceAll(replacement); }"
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

          <!-- Interface form -->
          <InterfaceForm v-else-if="yamlStore.isInterfaceCase" />
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

    <!-- Log panel -->
    <LogPanel />

    <!-- Param edit modal -->
    <ParamEditModal
      v-model:visible="paramEditVisible"
      :mode="paramEditMode"
      :file-path="currentFilePath"
    />
  </div>
</template>

<style scoped>
.yaml-editor-view {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
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
  min-height: 0;
}

.yaml-left-panel {
  width: 250px;
  min-width: 180px;
  flex-shrink: 0;
  min-height: 0;
  overflow-y: auto;
}

.yaml-center-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  min-width: 0;
}

.yaml-center-content {
  flex: 1;
  overflow: auto;
  min-height: 0;
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
