<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useWorkbookStore } from '../../stores/workbook'
import { useYamlStore } from '../../stores/yaml-store'
import { useEditorStore } from '../../stores/editor'

const route = useRoute()
const { t } = useI18n()
const workbook = useWorkbookStore()
const yamlStore = useYamlStore()
const editor = useEditorStore()

const isExcelMode = computed(() => route.name === 'excel-editor')
const isYamlMode = computed(() => route.name === 'yaml-editor')

const statusText = computed(() => {
  const modified = isExcelMode.value ? workbook.modified : yamlStore.modified
  if (modified) return t('status.modified')
  return t('status.ready')
})

const fileLabel = computed(() => {
  if (isExcelMode.value) {
    return workbook.filePath || workbook.fileName || t('menu.new')
  } else if (isYamlMode.value) {
    return yamlStore.currentFilePath || t('menu.new')
  }
  return ''
})

const editorLabel = computed(() => {
  if (isExcelMode.value) {
    return editor.activeSheet.name
  } else if (isYamlMode.value) {
    return yamlStore.currentCase?.case_type === 'single' ? 'Single Case' : 'Biz Flow'
  }
  return ''
})
</script>

<template>
  <footer class="status-bar">
    <span class="status-file">{{ fileLabel }}</span>
    <span>{{ statusText }}</span>
    <span class="status-mode">{{ editorLabel }}</span>
  </footer>
</template>

<style scoped>
.status-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 2px 12px;
  font-size: 12px;
  background: #f5f5f5;
  border-top: 1px solid #e8e8e8;
  height: 24px;
  color: #666;
}

.status-file {
  max-width: 400px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.status-mode {
  margin-left: auto;
}
</style>
