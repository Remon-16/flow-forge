import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type {
  ApiDefinition,
  SingleTestCase,
  BizFlow,
  BizStep,
  WorkbookData,
} from '../types/excel'
import { readExcelFromBuffer } from '../utils/excel-reader'
import { downloadExcel } from '../utils/excel-writer'
import { validateRelevanceID, findDuplicateStepIDs, validateTrans } from '../utils/validators'
import { isDesktop, writeFileBuffer, readFileBuffer, saveFileDialog } from '../utils/desktop-bridge'

let uidCounter = 0
function generateUid(): string {
  return `_uid_${Date.now()}_${++uidCounter}`
}

export const useWorkbookStore = defineStore('workbook', () => {
  // --- State ---
  const filePath = ref<string | null>(null)
  const fileName = ref<string | null>(null)
  const modified = ref(false)
  const loading = ref(false)

  const apiDefinitions = ref<ApiDefinition[]>([])
  const singleCases = ref<SingleTestCase[]>([])
  const bizFlows = ref<BizFlow[]>([])

  // --- Getters ---

  const validTestIds = computed(() => apiDefinitions.value.map((a) => a.TestID).filter(Boolean))

  const sheetCount = computed(() => 2 + bizFlows.value.length)

  // --- Actions ---

  async function openFile(file: File | string) {
    loading.value = true
    try {
      let buffer: ArrayBuffer
      let name: string | null = null
      let filePathToSet: string | null = null

      if (typeof file === 'string') {
        // Desktop mode: file is a path string
        buffer = await readFileBuffer(file)
        name = file.split(/[/\\]/).pop() || null
        filePathToSet = file
      } else {
        // Browser mode: file is a File object
        buffer = await new Promise<ArrayBuffer>((resolve, reject) => {
          const reader = new FileReader()
          reader.onload = () => resolve(reader.result as ArrayBuffer)
          reader.onerror = () => reject(new Error('Failed to read file'))
          reader.readAsArrayBuffer(file)
        })
        name = file.name
      }

      const data = readExcelFromBuffer(buffer)
      filePath.value = filePathToSet
      fileName.value = name
      apiDefinitions.value = data.apiDefinitions
      singleCases.value = data.singleCases
      bizFlows.value = data.bizFlows
      modified.value = false
      runAllValidations()
      loading.value = false
    } catch (err) {
      loading.value = false
      throw err
    }
  }

  function newWorkbook() {
    filePath.value = null
    fileName.value = null
    apiDefinitions.value = []
    singleCases.value = []
    bizFlows.value = []
    modified.value = false
  }

  async function save() {
    const data = buildData()
    try {
      if (isDesktop && filePath.value) {
        const { createWorkbook } = await import('../utils/excel-writer')
        const wb = await createWorkbook(data)
        const buffer = await wb.xlsx.writeBuffer()
        await writeFileBuffer(filePath.value, buffer)
      } else {
        const name = fileName.value || 'testcase.xlsx'
        await downloadExcel(data, name)
      }
      modified.value = false
    } catch (err) {
      console.error('Excel save failed:', err)
      throw err
    }
  }

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  async function saveAs() {
    const data = buildData()
    if (isDesktop) {
      const newPath = await saveFileDialog({
        filters: [{ name: 'Excel Files', extensions: ['xlsx'] }],
        defaultPath: fileName.value || 'testcase.xlsx',
      })
      if (newPath) {
        const { createWorkbook } = await import('../utils/excel-writer')
        const wb = await createWorkbook(data)
        const buffer = await wb.xlsx.writeBuffer()
        await writeFileBuffer(newPath, buffer)
        filePath.value = newPath
        fileName.value = newPath.split(/[/\\]/).pop() || null
      }
    } else {
      const name = fileName.value || 'testcase.xlsx'
      await downloadExcel(data, name)
    }
    modified.value = false
  }

  function buildData(): WorkbookData {
    return {
      apiDefinitions: apiDefinitions.value,
      singleCases: singleCases.value,
      bizFlows: bizFlows.value,
    }
  }

  // --- Mutations ---

  function markModified() {
    modified.value = true
  }

  // --- API Definitions ---

  function addApiDef() {
    apiDefinitions.value.push({
      _uid: generateUid(),
      TestID: '',
      APIName: '',
      AppName: '',
      Method: 'GET',
      URL: '',
      RequestHead: null,
      RequestBody: null,
      StatusCode: 200,
      AssertDict: null,
      AssertRules: null,
      Remark: '',
    })
    markModified()
  }

  function removeApiDef(index: number) {
    apiDefinitions.value.splice(index, 1)
    markModified()
    runAllValidations()
  }

  // --- Single Cases ---

  function addSingleCase() {
    singleCases.value.push({
      _uid: generateUid(),
      TestID: '',
      RelevanceID: '',
      Tag: 'P0',
      APIName: '',
      AppName: '',
      Method: 'GET',
      URL: '',
      RequestHead: null,
      RequestBody: null,
      StatusCode: 200,
      AssertDict: null,
      AssertRules: null,
      Remark: '',
      _relevanceValid: true,
    })
    markModified()
  }

  function removeSingleCase(index: number) {
    singleCases.value.splice(index, 1)
    markModified()
  }

  // --- Biz Flows ---

  function addBizFlow(name: string) {
    bizFlows.value.push({
      sheetName: name,
      steps: [],
    })
    markModified()
  }

  function removeBizFlow(index: number) {
    bizFlows.value.splice(index, 1)
    markModified()
  }

  function renameBizFlow(index: number, newName: string) {
    bizFlows.value[index].sheetName = newName
    markModified()
  }

  function addBizStep(flowIndex: number) {
    bizFlows.value[flowIndex].steps.push({
      _uid: generateUid(),
      StepID: '',
      RelevanceID: '',
      Trans: '',
      APIName: '',
      AppName: '',
      Method: 'GET',
      URL: '',
      RequestHead: null,
      RequestBody: null,
      StatusCode: 200,
      AssertDict: null,
      AssertRules: null,
      Tag: 'P0',
      Remark: '',
      _relevanceValid: true,
      _stepIdDuplicate: false,
      _transError: null,
    })
    markModified()
  }

  function removeBizStep(flowIndex: number, stepIndex: number) {
    bizFlows.value[flowIndex].steps.splice(stepIndex, 1)
    markModified()
    validateBizFlow(flowIndex)
  }

  function moveBizStep(flowIndex: number, stepIndex: number, direction: 'up' | 'down') {
    const steps = bizFlows.value[flowIndex].steps
    const targetIdx = direction === 'up' ? stepIndex - 1 : stepIndex + 1
    if (targetIdx < 0 || targetIdx >= steps.length) return
    ;[steps[stepIndex], steps[targetIdx]] = [steps[targetIdx], steps[stepIndex]]
    markModified()
  }

  // --- Validation ---

  function runAllValidations() {
    validateSingleCases()
    bizFlows.value.forEach((_, i) => validateBizFlow(i))
  }

  function validateSingleCases() {
    const ids = validTestIds.value
    for (const tc of singleCases.value) {
      const err = validateRelevanceID(tc.RelevanceID, ids)
      tc._relevanceValid = err === null
    }
  }

  function validateBizFlow(flowIndex: number) {
    const flow = bizFlows.value[flowIndex]
    const ids = validTestIds.value
    const dupes = findDuplicateStepIDs(flow.steps)

    for (const step of flow.steps) {
      // RelevanceID
      const relErr = validateRelevanceID(step.RelevanceID, ids)
      step._relevanceValid = relErr === null

      // StepID duplicate
      step._stepIdDuplicate = dupes.has(step.StepID?.trim())

      // Trans
      const transErr = validateTrans(step.Trans, step.StepID)
      step._transError = transErr
    }
  }

  function updateApiDefField(index: number, field: keyof ApiDefinition, value: unknown) {
    ;(apiDefinitions.value[index] as Record<string, unknown>)[field] = value
    markModified()
    // Re-validate since TestID changed
    if (field === 'TestID') {
      validateSingleCases()
      bizFlows.value.forEach((_, i) => validateBizFlow(i))
    }
  }

  function updateSingleCaseField(index: number, field: keyof SingleTestCase, value: unknown) {
    ;(singleCases.value[index] as Record<string, unknown>)[field] = value
    markModified()
    if (field === 'RelevanceID') {
      validateSingleCases()
    }
  }

  function updateBizStepField(
    flowIndex: number,
    stepIndex: number,
    field: keyof BizStep,
    value: unknown
  ) {
    ;(bizFlows.value[flowIndex].steps[stepIndex] as Record<string, unknown>)[field] = value
    markModified()
    validateBizFlow(flowIndex)
  }

  return {
    // state
    filePath,
    fileName,
    modified,
    loading,
    apiDefinitions,
    singleCases,
    bizFlows,
    // getters
    validTestIds,
    sheetCount,
    // actions
    openFile,
    newWorkbook,
    save,
    saveAs,
    buildData,
    markModified,
    // API defs
    addApiDef,
    removeApiDef,
    updateApiDefField,
    // single cases
    addSingleCase,
    removeSingleCase,
    updateSingleCaseField,
    // biz flows
    addBizFlow,
    removeBizFlow,
    renameBizFlow,
    addBizStep,
    removeBizStep,
    moveBizStep,
    updateBizStepField,
    // validation
    runAllValidations,
    validateSingleCases,
    validateBizFlow,
  }
})
