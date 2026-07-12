import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { YamlCase, SingleYamlCase, BizYamlCase, InterfaceYamlCase, YamlBizStep } from '../types/yaml'
import { createDefaultSingleCase, createDefaultBizCase, createDefaultInterfaceCase, createDefaultBizStep } from '../types/yaml'
import { parseYaml, stringifyYaml } from '../utils/yaml-parser'
import {
  isDesktop,
  readFile,
  writeFile,
  readDirectory,
  openDirectoryDialog,
  openFileDialog,
  saveFileDialog,
  renameFile as renameFileBackend,
  deleteToTrash as deleteToTrashBackend,
  copyFileOrDir as copyFileOrDirBackend,
  moveFileOrDir as moveFileOrDirBackend,
  openInExplorer as openInExplorerBackend,
} from '../utils/desktop-bridge'
import { findDuplicateStepIDs, validateInherit } from '../utils/validators'

export interface FileEntry {
  name: string
  path: string
  isDirectory: boolean
  children?: FileEntry[]
}

export interface OpenTab {
  path: string | null
  title: string
  case: YamlCase
  modified: boolean
}

interface FileClipboard {
  path: string
  mode: 'cut' | 'copy'
}

let untitledCounter = 0

export const useYamlStore = defineStore('yaml', () => {
  // --- State ---
  const rootPath = ref<string | null>(null)
  const fileTree = ref<FileEntry[]>([])
  const currentFilePath = ref<string | null>(null)
  const currentCase = ref<YamlCase | null>(null)
  const modified = ref(false)
  /** 状态版本号，每次 mutation 或 save 后递增，供 YamlRawView 等组件监听同步 */
  const _version = ref(0)
  const loading = ref(false)

  const openTabs = ref<OpenTab[]>([])
  const activeTabIndex = ref<number>(-1)

  const fileClipboard = ref<FileClipboard | null>(null)

  // --- Tab helpers ---

  function saveCurrentTabState() {
    const idx = activeTabIndex.value
    if (idx >= 0 && idx < openTabs.value.length) {
      openTabs.value[idx].case = currentCase.value!
      openTabs.value[idx].path = currentFilePath.value
      openTabs.value[idx].modified = modified.value
    }
  }

  function loadTabState(index: number) {
    const tab = openTabs.value[index]
    if (tab) {
      currentCase.value = tab.case
      currentFilePath.value = tab.path
      modified.value = tab.modified
    } else {
      currentCase.value = null
      currentFilePath.value = null
      modified.value = false
    }
  }

  // --- Getters ---
  const currentFileName = computed(() => {
    if (!currentFilePath.value) return null
    return currentFilePath.value.split(/[/\\]/).pop() || null
  })

  const isSingleCase = computed(() => currentCase.value?.case_type === 'single')
  const isBizCase = computed(() => currentCase.value?.case_type === 'biz')
  const isInterfaceCase = computed(() => currentCase.value?.case_type === 'interfaces')

  const hasUnsavedTabs = computed(() => openTabs.value.some(t => t.modified))

  const hasClipboard = computed(() => fileClipboard.value !== null)

  // --- Helpers ---

  function refreshFileTree() {
    if (!rootPath.value || !isDesktop) return
    readDirectory(rootPath.value).then((entries) => {
      fileTree.value = entries as unknown as FileEntry[]
    })
  }

  function splitDirAndName(filePath: string): { dir: string; name: string } {
    const normalized = filePath.replace(/\\/g, '/')
    const lastSlash = normalized.lastIndexOf('/')
    if (lastSlash < 0) return { dir: '', name: normalized }
    return { dir: normalized.substring(0, lastSlash), name: normalized.substring(lastSlash + 1) }
  }

  function splitNameExt(fileName: string): { base: string; ext: string } {
    const dotIdx = fileName.lastIndexOf('.')
    if (dotIdx <= 0) return { base: fileName, ext: '' }
    return { base: fileName.substring(0, dotIdx), ext: fileName.substring(dotIdx) }
  }

  function findEntryInTree(path: string, tree: FileEntry[]): FileEntry | null {
    for (const entry of tree) {
      if (entry.path === path) return entry
      if (entry.children) {
        const found = findEntryInTree(path, entry.children)
        if (found) return found
      }
    }
    return null
  }

  function nameExistsInDir(dirPath: string, name: string): boolean {
    const entry = findEntryInTree(dirPath, fileTree.value)
    if (!entry || !entry.children) return false
    return entry.children.some(c => c.name === name)
  }

  function collectDescendantPaths(entry: FileEntry): string[] {
    const paths: string[] = []
    if (!entry.isDirectory && entry.path) {
      paths.push(entry.path)
    }
    if (entry.children) {
      for (const child of entry.children) {
        paths.push(...collectDescendantPaths(child))
      }
    }
    return paths
  }

  // --- Actions ---

  async function openDirectory(dirPath?: string) {
    const targetPath = dirPath || (await openDirectoryDialog())
    if (!targetPath) return

    rootPath.value = targetPath

    if (isDesktop) {
      fileTree.value = await readDirectory(targetPath) as unknown as FileEntry[]
    } else {
      fileTree.value = []
    }
  }

  async function openFile(filePath?: string) {
    let targetPath: string | null | undefined = filePath
    if (!targetPath) {
      if (isDesktop) {
        targetPath = await openFileDialog(
          [{ name: 'YAML Files', extensions: ['yaml', 'yml'] }],
        )
      } else {
        // Browser fallback
        targetPath = await new Promise<string | null>((resolve) => {
          const input = document.createElement('input')
          input.type = 'file'
          input.accept = '.yaml,.yml'
          input.onchange = async () => {
            const file = input.files?.[0]
            if (!file) { resolve(null); return }
            try {
              const text = await file.text()
              const parsed = parseYaml(text)
              // Check if already open
              const existingIdx = openTabs.value.findIndex(t => t.path === file.name)
              if (existingIdx >= 0) {
                saveCurrentTabState()
                activeTabIndex.value = existingIdx
                loadTabState(existingIdx)
              } else {
                const title = file.name
                saveCurrentTabState()
                openTabs.value.push({ path: file.name, title, case: parsed, modified: false })
                activeTabIndex.value = openTabs.value.length - 1
                loadTabState(activeTabIndex.value)
              }
              runValidations()
              resolve(file.name)
            } catch (err) {
              console.error('Failed to open YAML file:', err)
              resolve(null)
            }
          }
          input.oncancel = () => resolve(null)
          input.click()
        })
        if (!targetPath) return
        return // Already processed above
      }
      if (!targetPath) return
    }

    // Check if file is already open in a tab (desktop mode)
    if (targetPath) {
      const existingIdx = openTabs.value.findIndex(t => t.path === targetPath)
      if (existingIdx >= 0) {
        saveCurrentTabState()
        activeTabIndex.value = existingIdx
        loadTabState(existingIdx)
        return
      }
    }

    loading.value = true
    try {
      const content = await readFile(targetPath)
      const parsed = parseYaml(content)
      const title = targetPath.split(/[/\\]/).pop() || targetPath
      saveCurrentTabState()
      openTabs.value.push({ path: targetPath, title, case: parsed, modified: false })
      activeTabIndex.value = openTabs.value.length - 1
      loadTabState(activeTabIndex.value)
      runValidations()
    } catch (err) {
      console.error('Failed to open YAML file:', err)
      throw err
    } finally {
      loading.value = false
    }
  }

  function downloadYamlBlob(yamlStr: string) {
    const blob = new Blob([yamlStr], { type: 'text/yaml' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = currentFileName.value || 'testcase.yaml'
    a.click()
    URL.revokeObjectURL(url)
  }

  async function save() {
    if (!currentCase.value) return

    // New file without a path: fall back to Save As
    if (!currentFilePath.value) {
      await saveAs()
      return
    }

    try {
      const yamlStr = stringifyYaml(currentCase.value)
      if (isDesktop) {
        await writeFile(currentFilePath.value, yamlStr)
      } else {
        downloadYamlBlob(yamlStr)
      }
      modified.value = false
      // Sync tab state
      saveCurrentTabState()
      _version.value++
    } catch (err) {
      console.error('Save failed:', err)
      throw err
    }
  }

  async function saveAs() {
    if (!currentCase.value) return

    if (isDesktop) {
      const newPath = await saveFileDialog({
        filters: [{ name: 'YAML Files', extensions: ['yaml', 'yml'] }],
        defaultPath: currentFileName.value || 'testcase.yaml',
      })
      if (!newPath) return
      currentFilePath.value = newPath
      // Update tab title and path
      const idx = activeTabIndex.value
      if (idx >= 0 && idx < openTabs.value.length) {
        openTabs.value[idx].path = newPath
        openTabs.value[idx].title = newPath.split(/[/\\]/).pop() || newPath
      }
      await save()
    } else {
      const yamlStr = stringifyYaml(currentCase.value)
      downloadYamlBlob(yamlStr)
      modified.value = false
      saveCurrentTabState()
    }
  }

  function newFile(caseType: 'single' | 'biz' | 'interfaces') {
    untitledCounter++
    const title = `Untitled-${untitledCounter}`
    let newCase: YamlCase
    if (caseType === 'single') {
      newCase = createDefaultSingleCase()
    } else if (caseType === 'biz') {
      newCase = createDefaultBizCase()
    } else {
      newCase = createDefaultInterfaceCase()
    }
    saveCurrentTabState()
    openTabs.value.push({ path: null, title, case: newCase, modified: true })
    activeTabIndex.value = openTabs.value.length - 1
    loadTabState(activeTabIndex.value)
  }

  function switchTab(index: number) {
    if (index < 0 || index >= openTabs.value.length) return
    saveCurrentTabState()
    activeTabIndex.value = index
    loadTabState(index)
  }

  function closeTab(index: number) {
    if (index < 0 || index >= openTabs.value.length) return
    openTabs.value.splice(index, 1)

    if (openTabs.value.length === 0) {
      activeTabIndex.value = -1
      currentCase.value = null
      currentFilePath.value = null
      modified.value = false
    } else if (activeTabIndex.value >= openTabs.value.length) {
      activeTabIndex.value = openTabs.value.length - 1
      loadTabState(activeTabIndex.value)
    } else if (activeTabIndex.value === index) {
      // Same index or we need to adjust
      if (activeTabIndex.value >= openTabs.value.length) {
        activeTabIndex.value = openTabs.value.length - 1
      }
      loadTabState(activeTabIndex.value)
    } else if (activeTabIndex.value > index) {
      activeTabIndex.value--
      loadTabState(activeTabIndex.value)
    }
  }

  function closeFile() {
    if (activeTabIndex.value >= 0) {
      closeTab(activeTabIndex.value)
    } else {
      currentFilePath.value = null
      currentCase.value = null
      modified.value = false
    }
  }

  async function renameFile(oldPath: string, newName: string) {
    const { dir } = splitDirAndName(oldPath)
    const separator = oldPath.includes('\\') ? '\\' : '/'
    const newPath = dir ? `${dir}${separator}${newName}` : newName
    await renameFileBackend(oldPath, newPath)

    for (const tab of openTabs.value) {
      if (tab.path === oldPath) {
        tab.path = newPath
        tab.title = newName
      }
    }
    if (currentFilePath.value === oldPath) {
      currentFilePath.value = newPath
    }
    refreshFileTree()
  }

  async function deleteFile(path: string) {
    const entry = findEntryInTree(path, fileTree.value)
    const pathsToClose: string[] = []
    if (entry && entry.isDirectory) {
      pathsToClose.push(...collectDescendantPaths(entry))
    }
    pathsToClose.push(path)

    await deleteToTrashBackend(path)

    const tabsToClose: number[] = []
    for (let i = 0; i < openTabs.value.length; i++) {
      const tabPath = openTabs.value[i].path
      if (tabPath && pathsToClose.some(p => tabPath === p || tabPath.startsWith(p + '/') || tabPath.startsWith(p + '\\'))) {
        tabsToClose.push(i)
      }
    }
    // Close from highest index to avoid shifting
    for (let i = tabsToClose.length - 1; i >= 0; i--) {
      closeTab(tabsToClose[i])
    }
    refreshFileTree()
  }

  function cutFile(path: string) {
    fileClipboard.value = { path, mode: 'cut' }
  }

  function copyFile(path: string) {
    fileClipboard.value = { path, mode: 'copy' }
  }

  async function pasteFile(targetPath: string) {
    if (!fileClipboard.value || !isDesktop) return
    const srcPath = fileClipboard.value.path
    const mode = fileClipboard.value.mode

    const targetEntry = findEntryInTree(targetPath, fileTree.value)
    let targetDir: string
    if (targetEntry && targetEntry.isDirectory) {
      targetDir = targetPath
    } else {
      const { dir } = splitDirAndName(targetPath)
      targetDir = dir
    }

    const { name: srcName } = splitDirAndName(srcPath)
    let destName = srcName
    if (nameExistsInDir(targetDir, destName)) {
      const { base, ext } = splitNameExt(srcName)
      let counter = 2
      do {
        destName = `${base} - Copy${ext}`
        if (counter > 2) {
          destName = `${base} - Copy (${counter})${ext}`
        }
        counter++
      } while (nameExistsInDir(targetDir, destName))
    }

    const separator = targetDir.includes('\\') ? '\\' : '/'
    const destPath = targetDir ? `${targetDir}${separator}${destName}` : destName

    if (mode === 'cut') {
      await moveFileOrDirBackend(srcPath, destPath)
      fileClipboard.value = null
      for (const tab of openTabs.value) {
        if (tab.path === srcPath) {
          tab.path = destPath
          tab.title = destName
        }
      }
      if (currentFilePath.value === srcPath) {
        currentFilePath.value = destPath
      }
    } else {
      await copyFileOrDirBackend(srcPath, destPath)
    }
    refreshFileTree()
  }

  async function openInExplorer(path: string) {
    await openInExplorerBackend(path)
  }

  // --- Mutations ---

  function markModified() {
    modified.value = true
    _version.value++
    const idx = activeTabIndex.value
    if (idx >= 0 && idx < openTabs.value.length) {
      openTabs.value[idx].modified = true
      if (currentCase.value) {
        openTabs.value[idx].case = currentCase.value
      }
    }
  }

  // Single case field update
  function updateSingleField(field: keyof SingleYamlCase, value: unknown) {
    if (!isSingleCase.value || !currentCase.value) return
    currentCase.value = { ...currentCase.value, [field]: value }
    markModified()
  }

  // Interface case field update
  function updateInterfaceField(field: keyof InterfaceYamlCase, value: unknown) {
    if (!isInterfaceCase.value || !currentCase.value) return
    currentCase.value = { ...currentCase.value, [field]: value }
    markModified()
  }

  // Biz flow field update
  function updateBizField(field: 'sheet_name', value: unknown) {
    if (!isBizCase.value || !currentCase.value) return
    currentCase.value = { ...currentCase.value, [field]: value } as BizYamlCase
    markModified()
  }

  function addBizStep() {
    if (!isBizCase.value) return
    const bizCase = currentCase.value as BizYamlCase
    currentCase.value = { ...bizCase, steps: [...bizCase.steps, createDefaultBizStep()] }
    markModified()
  }

  function removeBizStep(index: number) {
    if (!isBizCase.value) return
    const bizCase = currentCase.value as BizYamlCase
    const steps = [...bizCase.steps]
    steps.splice(index, 1)
    currentCase.value = { ...bizCase, steps }
    markModified()
    validateBizSteps()
  }

  function moveBizStep(index: number, direction: 'up' | 'down') {
    if (!isBizCase.value) return
    const bizCase = currentCase.value as BizYamlCase
    const steps = [...bizCase.steps]
    const targetIdx = direction === 'up' ? index - 1 : index + 1
    if (targetIdx < 0 || targetIdx >= steps.length) return
    ;[steps[index], steps[targetIdx]] = [steps[targetIdx], steps[index]]
    currentCase.value = { ...bizCase, steps }
    markModified()
  }

  function updateBizStepField(stepIndex: number, field: keyof YamlBizStep, value: unknown) {
    if (!isBizCase.value) return
    const bizCase = currentCase.value as BizYamlCase
    const steps = [...bizCase.steps]
    steps[stepIndex] = { ...steps[stepIndex], [field]: value }
    currentCase.value = { ...bizCase, steps }
    markModified()
    validateBizSteps()
  }

  // --- YAML Validation ---

  function runValidations() {
    if (isBizCase.value && currentCase.value) {
      validateBizSteps()
    }
  }

  function validateBizSteps() {
    if (!isBizCase.value) return
    const bizCase = currentCase.value as BizYamlCase
    const dupes = findDuplicateStepIDs(bizCase.steps.map(toValidationStep))

    for (const step of bizCase.steps) {
      ;(step as any)._stepIdDuplicate = dupes.has(step.step_id?.trim())
      ;(step as any)._inheritError = validateInherit(step.inherit, step.step_id)
      ;(step as any)._urlWarning = (step.url || '').includes('<URL not exist>')
    }
  }

  function toValidationStep(s: YamlBizStep) {
    return {
      StepID: s.step_id,
      RelevanceID: s.relevance_id,
      Inherit: s.inherit,
      _uid: '',
      TestID: s.step_id,
      Tag: s.tag,
      APIName: s.api_name,
      AppName: s.app_name,
      Method: s.method,
      URL: s.url,
      RequestHead: s.request_head,
      RequestBody: s.request_body,
      StatusCode: s.status_code,
      AssertDict: s.assert_dict,
      AssertRules: s.assert_rules,
      Remark: s.remark,
    }
  }

  return {
    // state
    rootPath,
    fileTree,
    currentFilePath,
    currentCase,
    modified,
    _version,
    loading,
    openTabs,
    activeTabIndex,
    fileClipboard,
    // getters
    currentFileName,
    isSingleCase,
    isBizCase,
    isInterfaceCase,
    hasUnsavedTabs,
    hasClipboard,
    // actions
    openDirectory,
    openFile,
    save,
    saveAs,
    newFile,
    closeFile,
    switchTab,
    closeTab,
    renameFile,
    deleteFile,
    cutFile,
    copyFile,
    pasteFile,
    openInExplorer,
    refreshFileTree,
    // mutations
    markModified,
    updateSingleField,
    updateInterfaceField,
    updateBizField,
    addBizStep,
    removeBizStep,
    moveBizStep,
    updateBizStepField,
    runValidations,
  }
})
