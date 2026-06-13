import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { YamlCase, SingleYamlCase, BizYamlCase, YamlBizStep } from '../types/yaml'
import { createDefaultSingleCase, createDefaultBizCase, createDefaultBizStep } from '../types/yaml'
import { parseYaml, stringifyYaml } from '../utils/yaml-parser'
import {
  isDesktop,
  readFile,
  writeFile,
  readDirectory,
  openDirectoryDialog,
  openFileDialog,
  saveFileDialog,
} from '../utils/desktop-bridge'
import { findDuplicateStepIDs, validateTrans } from '../utils/validators'

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

let untitledCounter = 0

export const useYamlStore = defineStore('yaml', () => {
  // --- State ---
  const rootPath = ref<string | null>(null)
  const fileTree = ref<FileEntry[]>([])
  const currentFilePath = ref<string | null>(null)
  const currentCase = ref<YamlCase | null>(null)
  const modified = ref(false)
  const loading = ref(false)

  const openTabs = ref<OpenTab[]>([])
  const activeTabIndex = ref<number>(-1)

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

  const hasUnsavedTabs = computed(() => openTabs.value.some(t => t.modified))

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

  function newFile(caseType: 'single' | 'biz') {
    untitledCounter++
    const title = `Untitled-${untitledCounter}`
    const newCase = caseType === 'single'
      ? createDefaultSingleCase()
      : createDefaultBizCase()
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

  // --- Mutations ---

  function markModified() {
    modified.value = true
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
      ;(step as any)._transError = validateTrans(step.trans, step.step_id)
    }
  }

  function toValidationStep(s: YamlBizStep) {
    return {
      StepID: s.step_id,
      RelevanceID: s.relevance_id,
      Trans: s.trans,
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
    loading,
    openTabs,
    activeTabIndex,
    // getters
    currentFileName,
    isSingleCase,
    isBizCase,
    hasUnsavedTabs,
    // actions
    openDirectory,
    openFile,
    save,
    saveAs,
    newFile,
    closeFile,
    switchTab,
    closeTab,
    // mutations
    markModified,
    updateSingleField,
    updateBizField,
    addBizStep,
    removeBizStep,
    moveBizStep,
    updateBizStepField,
    runValidations,
  }
})
