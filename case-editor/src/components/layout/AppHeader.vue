<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useWorkbookStore } from '../../stores/workbook'
import { useSettingsStore } from '../../stores/settings'
import { downloadExcel } from '../../utils/excel-writer'
import { onMounted, onUnmounted } from 'vue'

const { t } = useI18n()
const workbook = useWorkbookStore()
const settings = useSettingsStore()

function handleNew() {
  workbook.newWorkbook()
}

function handleOpen() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.xlsx,.xls'
  input.onchange = async (e) => {
    const file = (e.target as HTMLInputElement).files?.[0]
    if (!file) return
    const path = (file as unknown as { path?: string }).path || file.name
    workbook.openFile(path)
  }
  input.click()
}

async function handleSave() {
  try {
    workbook.save()
  } catch {
    await handleSaveAs()
  }
}

function handleSaveAs() {
  const data = workbook.buildData()
  const name = workbook.filePath
    ? workbook.filePath.split('/').pop() || 'testcase.xlsx'
    : 'testcase.xlsx'
  downloadExcel(data, name)
  workbook.filePath = name
  workbook.modified = false
}

function handleLanguageChange(lang: string) {
  settings.setLanguage(lang as 'zh-CN' | 'en-US')
}

// Keyboard shortcuts
function onKeyDown(e: KeyboardEvent) {
  if (e.ctrlKey && e.altKey && e.key === 's') {
    e.preventDefault()
    handleSaveAs()
  } else if (e.ctrlKey && e.key === 's') {
    e.preventDefault()
    handleSave()
  } else if (e.ctrlKey && e.key === 'o') {
    e.preventDefault()
    handleOpen()
  } else if (e.ctrlKey && e.key === 'n') {
    e.preventDefault()
    handleNew()
  }
}

onMounted(() => window.addEventListener('keydown', onKeyDown))
onUnmounted(() => window.removeEventListener('keydown', onKeyDown))
</script>

<template>
  <header class="app-header">
    <span style="font-weight: 600; margin-right: 16px; font-size: 14px; white-space: nowrap;">
      {{ t('header.title') }}
    </span>

    <a-button size="small" type="text" @click="handleNew">{{ t('menu.new') }}</a-button>
    <a-button size="small" type="text" @click="handleOpen">{{ t('menu.open') }}</a-button>
    <a-button size="small" type="text" @click="handleSave">{{ t('menu.save') }}</a-button>
    <a-button size="small" type="text" @click="handleSaveAs">{{ t('menu.saveAs') }}</a-button>

    <a-divider type="vertical" />

    <a-select
      :value="settings.language"
      size="small"
      style="width: 90px"
      @change="handleLanguageChange"
    >
      <a-select-option value="zh-CN">中文</a-select-option>
      <a-select-option value="en-US">English</a-select-option>
    </a-select>
  </header>
</template>
