<script setup lang="ts">
import { useEditorStore } from '../stores/editor'
import { useWorkbookStore } from '../stores/workbook'
import { useI18n } from 'vue-i18n'
import ApiDefEditor from '../components/editor/ApiDefEditor.vue'
import SingleCaseEditor from '../components/editor/SingleCaseEditor.vue'
import BizFlowEditor from '../components/editor/BizFlowEditor.vue'

const { t } = useI18n()
const editor = useEditorStore()
const workbook = useWorkbookStore()
</script>

<template>
  <div style="height: 100%; display: flex; flex-direction: column;">
    <!-- API Definitions -->
    <ApiDefEditor v-if="editor.activeSheetIndex === -1" />

    <!-- Single Cases -->
    <SingleCaseEditor v-else-if="editor.activeSheetIndex === 0" />

    <!-- Biz Flow -->
    <BizFlowEditor
      v-else
      :flow-index="editor.activeSheetIndex - 1"
    />

    <!-- Empty state -->
    <div
      v-if="workbook.apiDefinitions.length === 0 && editor.activeSheetIndex === -1"
      style="display: flex; align-items: center; justify-content: center; height: 100%; color: #999;"
    >
      {{ t('table.noData') }}
    </div>
  </div>
</template>
