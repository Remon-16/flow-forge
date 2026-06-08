import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type {
  ApiDefinition,
  SingleTestCase,
  BizFlow,
  BizStep,
  WorkbookData,
} from '../types/excel'
import { readExcel } from '../utils/excel-reader'
import { writeExcel } from '../utils/excel-writer'
import { validateRelevanceID, findDuplicateStepIDs, validateTrans } from '../utils/validators'

export const useWorkbookStore = defineStore('workbook', () => {
  // --- State ---
  const filePath = ref<string | null>(null)
  const modified = ref(false)

  const apiDefinitions = ref<ApiDefinition[]>([])
  const singleCases = ref<SingleTestCase[]>([])
  const bizFlows = ref<BizFlow[]>([])

  // --- Getters ---

  const validTestIds = computed(() => apiDefinitions.value.map((a) => a.TestID).filter(Boolean))

  const sheetCount = computed(() => 2 + bizFlows.value.length)

  // --- Actions ---

  function openFile(path: string) {
    const data = readExcel(path)
    filePath.value = path
    apiDefinitions.value = data.apiDefinitions
    singleCases.value = data.singleCases
    bizFlows.value = data.bizFlows
    modified.value = false
    runAllValidations()
  }

  function newWorkbook() {
    filePath.value = null
    apiDefinitions.value = []
    singleCases.value = []
    bizFlows.value = []
    modified.value = false
  }

  function save() {
    if (!filePath.value) {
      throw new Error('请先使用"另存为"选择保存路径')
    }
    const data = buildData()
    writeExcel(filePath.value, data)
    modified.value = false
  }

  function saveAs(path: string) {
    const data = buildData()
    writeExcel(path, data)
    filePath.value = path
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
      TestID: '',
      APIName: '',
      AppName: '',
      Method: 'GET',
      URL: '',
      RequestHead: {},
      RequestBody: {},
      StatusCode: 200,
      AssertDict: {},
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
      TestID: '',
      RelevanceID: '',
      Tag: 'P0',
      APIName: '',
      AppName: '',
      Method: 'GET',
      URL: '',
      RequestHead: {},
      RequestBody: {},
      StatusCode: 200,
      AssertDict: {},
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
      StepID: '',
      RelevanceID: '',
      Trans: '',
      APIName: '',
      AppName: '',
      Method: 'GET',
      URL: '',
      RequestHead: {},
      RequestBody: {},
      StatusCode: 200,
      AssertDict: {},
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
    modified,
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
