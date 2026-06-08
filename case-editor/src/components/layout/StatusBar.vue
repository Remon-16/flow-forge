<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useWorkbookStore } from '../../stores/workbook'
import { useEditorStore } from '../../stores/editor'
import { computed } from 'vue'

const { t } = useI18n()
const workbook = useWorkbookStore()
const editor = useEditorStore()

const statusText = computed(() => {
  if (workbook.modified) return t('status.modified')
  return t('status.ready')
})

const fileLabel = computed(() => workbook.filePath || t('menu.new'))
</script>

<template>
  <footer class="status-bar">
    <span>{{ fileLabel }}</span>
    <span>{{ statusText }}</span>
    <span style="margin-left: auto;">{{ editor.activeSheet.name }}</span>
  </footer>
</template>
