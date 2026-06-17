<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

export interface AnnotationData {
  line_number: number
  selected_text: string
  review_comment: string
}

const props = defineProps<{
  visible: boolean
  selectedText: string
  lineNumber: number
  existingComment?: string
}>()

const emit = defineEmits<{
  close: []
  save: [data: AnnotationData]
}>()

const { t } = useI18n()
const comment = ref('')

watch(() => props.visible, (val) => {
  if (val) {
    comment.value = props.existingComment || ''
  }
})

function handleSave() {
  if (!comment.value.trim()) return
  emit('save', {
    line_number: props.lineNumber,
    selected_text: props.selectedText,
    review_comment: comment.value.trim(),
  })
  comment.value = ''
}

function handleCancel() {
  comment.value = ''
  emit('close')
}
</script>

<template>
  <a-modal
    :open="visible"
    :title="existingComment ? t('annotator.editAnnotation') : t('annotator.addAnnotation')"
    :ok-text="t('annotator.save')"
    :cancel-text="t('annotator.cancel')"
    @ok="handleSave"
    @cancel="handleCancel"
    :ok-button-props="{ disabled: !comment.trim() }"
  >
    <div style="margin-bottom: 12px;">
      <div style="color: #888; font-size: 12px; margin-bottom: 4px;">{{ t('annotator.selectedText') }}</div>
      <div style="background: #f5f5f5; padding: 8px 12px; border-radius: 4px; font-size: 13px; word-break: break-all;">
        {{ selectedText }}
      </div>
    </div>

    <div style="margin-bottom: 12px;">
      <div style="color: #888; font-size: 12px; margin-bottom: 4px;">{{ t('annotator.lineNumber') }}</div>
      <div style="font-size: 13px;">{{ lineNumber }}</div>
    </div>

    <div>
      <div style="color: #888; font-size: 12px; margin-bottom: 4px;">{{ t('annotator.comment') }}</div>
      <a-textarea
        v-model:value="comment"
        :placeholder="t('annotator.commentPlaceholder')"
        :rows="4"
      />
    </div>
  </a-modal>
</template>
