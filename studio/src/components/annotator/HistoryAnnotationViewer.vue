<script setup lang="ts">
import { useI18n } from 'vue-i18n'

export interface AnnotationData {
  line_number: number
  selected_text: string
  review_comment: string
}

const props = defineProps<{
  visible: boolean
  fileName: string
  annotations: AnnotationData[]
}>()

const emit = defineEmits<{
  close: []
}>()

const { t } = useI18n()
</script>

<template>
  <a-modal
    :open="visible"
    :title="t('annotator.viewOnly')"
    :footer="null"
    width="640px"
    @cancel="emit('close')"
  >
    <div style="margin-bottom: 12px; color: #666; font-size: 13px;">
      {{ t('annotator.fileName') }}: {{ fileName }}
      &nbsp;({{ t('annotator.annotationCount', { count: annotations.length }) }})
    </div>

    <div v-if="annotations.length === 0" style="color: #999; text-align: center; padding: 24px;">
      {{ t('annotator.noAnnotations') }}
    </div>

    <div
      v-for="(ann, idx) in annotations"
      :key="idx"
      style="border: 1px solid #e8e8e8; border-radius: 6px; padding: 12px; margin-bottom: 8px;"
    >
      <div style="display: flex; gap: 16px; margin-bottom: 6px; font-size: 12px; color: #888;">
        <span>#{{ idx + 1 }}</span>
        <span>{{ t('annotator.lineNumber') }}: {{ ann.line_number }}</span>
      </div>
      <div style="background: #f5f5f5; padding: 6px 10px; border-radius: 4px; font-size: 12px; margin-bottom: 6px; word-break: break-all;">
        {{ ann.selected_text }}
      </div>
      <div style="font-size: 13px; color: #333;">
        {{ ann.review_comment }}
      </div>
    </div>
  </a-modal>
</template>
