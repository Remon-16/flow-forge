<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { useWorkbookStore } from '../../stores/workbook'
import { useYamlStore } from '../../stores/yaml-store'
import { useSettingsStore } from '../../stores/settings'
import { isDesktop, openFileDialog } from '../../utils/desktop-bridge'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const workbook = useWorkbookStore()
const yamlStore = useYamlStore()
const settings = useSettingsStore()

const isExcelMode = computed(() => route.name === 'excel-editor')
const isYamlMode = computed(() => route.name === 'yaml-editor')
const modeTitle = computed(() => isExcelMode.value ? t('header.excelEditor') : t('header.yamlEditor'))

function goHome() {
  router.push('/')
}

function handleNew() {
  if (isExcelMode.value) {
    workbook.newWorkbook()
    message.info(t('yaml.newFileCreated'))
  } else {
    yamlStore.newFile('single')
    message.info(t('yaml.newFileCreated'))
  }
}

async function handleOpen() {
  if (isExcelMode.value) {
    if (isDesktop) {
      const filePath = await openFileDialog(
        [{ name: 'Excel Files', extensions: ['xlsx', 'xls'] }],
      )
      if (filePath) {
        await workbook.openFile(filePath)
      }
    } else {
      const input = document.createElement('input')
      input.type = 'file'
      input.accept = '.xlsx,.xls'
      input.onchange = async (e) => {
        const file = (e.target as HTMLInputElement).files?.[0]
        if (!file) return
        try { await workbook.openFile(file) } catch (err) { console.error(err) }
      }
      input.click()
    }
  } else {
    yamlStore.openFile()
  }
}

function handleOpenMenuClick({ key }: { key: string }) {
  if (key === 'open-directory') {
    yamlStore.openDirectory()
  } else if (key === 'open-file') {
    yamlStore.openFile()
  }
}

async function handleSave() {
  try {
    if (isExcelMode.value) {
      await workbook.save()
    } else {
      await yamlStore.save()
    }
    message.success(t('yaml.saved'))
  } catch (err) {
    console.error('Save failed:', err)
    message.error(t('yaml.saveFailed'))
  }
}

async function handleSaveAs() {
  try {
    if (isExcelMode.value) {
      await workbook.saveAs()
    } else {
      await yamlStore.saveAs()
    }
  } catch (err) {
    console.error('Save As failed:', err)
  }
}

function handleLanguageChange(lang: string) {
  settings.setLanguage(lang as 'zh-CN' | 'en-US')
}

// Keyboard shortcuts
function onKeyDown(e: KeyboardEvent) {
  if (e.ctrlKey && e.key === 's' && !e.altKey) {
    e.preventDefault()
    handleSave()
  } else if (e.ctrlKey && e.altKey && e.key === 's') {
    e.preventDefault()
    handleSaveAs()
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
    <a-button size="small" type="text" @click="goHome">
      &#8592; {{ t('header.backHome') }}
    </a-button>

    <span style="font-weight: 600; margin: 0 16px; font-size: 14px; white-space: nowrap;">
      {{ modeTitle }}
    </span>

    <a-button size="small" type="text" @click="handleNew">{{ t('menu.new') }}</a-button>

    <a-dropdown v-if="isYamlMode">
      <a-button size="small" type="text">{{ t('menu.open') }}</a-button>
      <template #overlay>
        <a-menu @click="handleOpenMenuClick">
          <a-menu-item key="open-directory">
            <span>&#128193;</span> {{ t('yaml.openDir') }}
          </a-menu-item>
          <a-menu-item key="open-file">
            <span>&#128196;</span> {{ t('yaml.openFile') }}
          </a-menu-item>
        </a-menu>
      </template>
    </a-dropdown>
    <a-button v-else size="small" type="text" @click="handleOpen">{{ t('menu.open') }}</a-button>

    <a-button size="small" type="text" @click="handleSave">{{ t('yaml.save') }}</a-button>
    <a-button size="small" type="text" @click="handleSaveAs">{{ t('yaml.saveAs') }}</a-button>

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
