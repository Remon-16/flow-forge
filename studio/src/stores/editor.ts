import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { ActiveSheet, SheetType } from '../types/editor'

export type SearchActionType = 'find' | 'replace' | 'findInFiles' | 'replaceInFiles'

export const useEditorStore = defineStore('editor', () => {
  const activeSheetIndex = ref(-1) // -1=apiDef, 0=singleCase, 1+=bizFlow

  const activeSheetType = computed<SheetType>(() => {
    if (activeSheetIndex.value === -1) return 'apiDef'
    if (activeSheetIndex.value === 0) return 'singleCase'
    return 'bizFlow'
  })

  const activeSheet = computed<ActiveSheet>(() => ({
    index: activeSheetIndex.value,
    type: activeSheetType.value,
    name:
      activeSheetType.value === 'apiDef'
        ? '接口定义'
        : activeSheetType.value === 'singleCase'
          ? '单接口用例'
          : `业务链路 #${activeSheetIndex.value}`,
  }))

  function setActiveSheet(index: number) {
    activeSheetIndex.value = index
  }

  // Search action trigger (cross-component communication)
  const searchAction = ref<{ type: SearchActionType } | null>(null)

  function triggerSearch(type: SearchActionType) {
    searchAction.value = { type }
  }

  function clearSearchAction() {
    searchAction.value = null
  }

  return { activeSheetIndex, activeSheetType, activeSheet, setActiveSheet, searchAction, triggerSearch, clearSearchAction }
})
