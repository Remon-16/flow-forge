<!-- Chunk 编辑对话框 / Chunk editor dialog.
     隐藏 schema 其余字段，只展示 content 和 mermaid（仅 biz 类型）。
     Hides schema fields; only shows content and mermaid (biz type only). -->

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'

const { t } = useI18n()

const props = defineProps<{
  visible: boolean
  chunkId: string
  chunkName: string
  chunkType: 'api' | 'biz'
  content: string
  mermaid: string
}>()

const emit = defineEmits<{
  close: []
  save: [content: string, mermaid: string]
}>()

const editContent = ref('')
const editMermaid = ref('')

watch(() => props.visible, (v) => {
  if (v) {
    editContent.value = props.content || ''
    editMermaid.value = props.mermaid || ''
  }
})

function onSave() {
  if (!editContent.value.trim()) {
    message.warning(t('annotator.emptyContent'))
    return
  }
  emit('save', editContent.value, editMermaid.value)
}

function onClose() {
  emit('close')
}
</script>

<template>
  <a-modal
    :open="visible"
    :title="`${t('annotator.editChunk')}: ${chunkName} (${chunkId})`"
    width="800px"
    @ok="onSave"
    @cancel="onClose"
  >
    <div class="chunk-editor">
      <!-- Content -->
      <div class="editor-field">
        <label>{{ t('annotator.content') }} (Markdown)</label>
        <a-textarea
          v-model:value="editContent"
          :rows="12"
          placeholder="Markdown content..."
        />
      </div>

      <!-- Mermaid (仅 biz 类型) / Mermaid (biz type only) -->
      <div v-if="chunkType === 'biz'" class="editor-field" style="margin-top: 16px;">
        <label>{{ t('annotator.mermaid') }}</label>
        <a-textarea
          v-model:value="editMermaid"
          :rows="8"
          placeholder="```mermaid&#10;sequenceDiagram&#10;...&#10;```"
          style="font-family: monospace;"
        />
      </div>
    </div>
  </a-modal>
</template>

<style scoped>
.chunk-editor {
  padding: 8px 0;
}
.editor-field label {
  display: block;
  font-weight: 600;
  margin-bottom: 6px;
  font-size: 13px;
  color: #333;
}
</style>
