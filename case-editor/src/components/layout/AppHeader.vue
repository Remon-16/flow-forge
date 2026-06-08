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

async function handleOpen() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.xlsx,.xls'
  input.onchange = async (e) => {
    const file = (e.target as HTMLInputElement).files?.[0]
    if (!file) return
    try {
      await workbook.openFile(file)
    } catch (err) {
      console.error('打开文件失败:', err)
    }
  }
  input.click()
}

function handleExport() {
  const data = workbook.buildData()
  const name = workbook.fileName || 'testcase.xlsx'
  downloadExcel(data, name)
  workbook.modified = false
}

function handleLanguageChange(lang: string) {
  settings.setLanguage(lang as 'zh-CN' | 'en-US')
}

// Keyboard shortcuts
function onKeyDown(e: KeyboardEvent) {
  if (e.ctrlKey && e.key === 's') {
    e.preventDefault()
    handleExport()
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
    <a-button size="small" type="text" @click="handleExport">{{ t('menu.export') }}</a-button>

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
