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

export const useYamlStore = defineStore('yaml', () => {
  // --- State ---
  const rootPath = ref<string | null>(null)
  const fileTree = ref<FileEntry[]>([])
  const currentFilePath = ref<string | null>(null)
  const currentCase = ref<YamlCase | null>(null)
  const modified = ref(false)
  const loading = ref(false)

  // --- Getters ---
  const currentFileName = computed(() => {
    if (!currentFilePath.value) return null
    return currentFilePath.value.split(/[/\\]/).pop() || null
  })

  const isSingleCase = computed(() => currentCase.value?.case_type === 'single')
  const isBizCase = computed(() => currentCase.value?.case_type === 'biz')

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
    // If no explicit path, use file dialog
    let targetPath = filePath
    if (!targetPath) {
      if (isDesktop) {
        targetPath = await openFileDialog({
          filters: [{ name: 'YAML Files', extensions: ['yaml', 'yml'] }],
        })
      }
      if (!targetPath) return
    }

    loading.value = true
    try {
      const content = await readFile(targetPath)
      const parsed = parseYaml(content)
      currentFilePath.value = targetPath
      currentCase.value = parsed
      modified.value = false
      runValidations()
    } catch (err) {
      console.error('Failed to open YAML file:', err)
      throw err
    } finally {
      loading.value = false
    }
  }

  async function save() {
    if (!currentFilePath.value || !currentCase.value) return

    const yamlStr = stringifyYaml(currentCase.value)
    await writeFile(currentFilePath.value, yamlStr)
    modified.value = false
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
      await save()
    } else {
      // Browser fallback: download
      const yamlStr = stringifyYaml(currentCase.value)
      const blob = new Blob([yamlStr], { type: 'text/yaml' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = currentFileName.value || 'testcase.yaml'
      a.click()
      URL.revokeObjectURL(url)
      modified.value = false
    }
  }

  function newFile(caseType: 'single' | 'biz') {
    currentFilePath.value = null
    currentCase.value = caseType === 'single'
      ? createDefaultSingleCase()
      : createDefaultBizCase()
    modified.value = true
  }

  function closeFile() {
    currentFilePath.value = null
    currentCase.value = null
    modified.value = false
  }

  // --- Mutations ---

  function markModified() {
    modified.value = true
  }

  // Single case field update
  function updateSingleField(field: keyof SingleYamlCase, value: unknown) {
    if (!isSingleCase.value || !currentCase.value) return
    ;(currentCase.value as Record<string, unknown>)[field] = value
    markModified()
  }

  // Biz flow field update
  function updateBizField(field: 'sheet_name', value: unknown) {
    if (!isBizCase.value || !currentCase.value) return
    ;(currentCase.value as Record<string, unknown>)[field] = value
    markModified()
  }

  function addBizStep() {
    if (!isBizCase.value) return
    ;(currentCase.value as BizYamlCase).steps.push(createDefaultBizStep())
    markModified()
  }

  function removeBizStep(index: number) {
    if (!isBizCase.value) return
    ;(currentCase.value as BizYamlCase).steps.splice(index, 1)
    markModified()
    validateBizSteps()
  }

  function moveBizStep(index: number, direction: 'up' | 'down') {
    if (!isBizCase.value) return
    const steps = (currentCase.value as BizYamlCase).steps
    const targetIdx = direction === 'up' ? index - 1 : index + 1
    if (targetIdx < 0 || targetIdx >= steps.length) return
    ;[steps[index], steps[targetIdx]] = [steps[targetIdx], steps[index]]
    markModified()
  }

  function updateBizStepField(stepIndex: number, field: keyof YamlBizStep, value: unknown) {
    if (!isBizCase.value) return
    const step = (currentCase.value as BizYamlCase).steps[stepIndex]
    ;(step as unknown as Record<string, unknown>)[field] = value
    markModified()
    validateBizSteps()
  }

  // --- YAML Validation ---
  // YAML validation doesn't need test_id reference like Excel does,
  // since YAML files are self-contained. But we validate StepID duplicates and Trans format.

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
      ;(step as any)._stepIdDuplicate = dupes.has(step.StepID?.trim())
      ;(step as any)._transError = validateTrans(step.Trans, step.StepID)
    }
  }

  function toValidationStep(s: YamlBizStep) {
    return {
      StepID: s.StepID,
      RelevanceID: s.RelevanceID,
      Trans: s.Trans,
      _uid: '',
      TestID: s.StepID,
      Tag: s.Tag,
      APIName: s.APIName,
      AppName: s.AppName,
      Method: s.Method,
      URL: s.URL,
      RequestHead: s.RequestHead,
      RequestBody: s.RequestBody,
      StatusCode: s.StatusCode,
      AssertDict: s.AssertDict,
      AssertRules: s.AssertRules,
      Remark: s.Remark,
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
    // getters
    currentFileName,
    isSingleCase,
    isBizCase,
    // actions
    openDirectory,
    openFile,
    save,
    saveAs,
    newFile,
    closeFile,
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
