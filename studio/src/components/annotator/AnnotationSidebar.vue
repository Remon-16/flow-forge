<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { AnnotationData } from './MarkdownPreview.vue'

export interface HistoryGroup {
  name: string
  path: string
  annotations: AnnotationData[]
}

const props = defineProps<{
  annotations: AnnotationData[]
  historyGroups: HistoryGroup[]
}>()

const emit = defineEmits<{
  'edit': [index: number]
  'delete': [index: number]
  'scroll-to': [index: number]
  'view-history': [group: HistoryGroup]
}>()

const { t } = useI18n()

function previewText(comment: string): string {
  return comment.length > 20 ? comment.substring(0, 20) + '...' : comment
}
</script>

<template>
  <div class="annotation-sidebar">
    <!-- Current Annotations -->
    <div class="sidebar-section">
      <div class="sidebar-section-header">
        {{ t('annotator.currentAnnotations') }}
        <a-tag v-if="annotations.length" color="blue" size="small">{{ annotations.length }}</a-tag>
      </div>

      <div v-if="annotations.length === 0" class="empty-hint">
        {{ t('annotator.noAnnotations') }}
      </div>

      <div class="annotation-list">
        <div
          v-for="(ann, idx) in annotations"
          :key="idx"
          class="annotation-item"
          @click="emit('scroll-to', idx)"
        >
          <div class="annotation-item-header">
            <span class="annotation-index">#{{ idx + 1 }}</span>
            <span class="annotation-line">L{{ ann.line_number }}</span>
          </div>
          <div class="annotation-item-body">
            {{ previewText(ann.review_comment) }}
          </div>
          <div class="annotation-item-actions">
            <a-button size="small" type="link" @click.stop="emit('edit', idx)">
              {{ t('annotator.editAnnotation') }}
            </a-button>
            <a-button size="small" type="link" danger @click.stop="emit('delete', idx)">
              {{ t('annotator.deleteAnnotation') }}
            </a-button>
          </div>
        </div>
      </div>
    </div>

    <!-- History Annotations -->
    <div class="sidebar-section">
      <a-collapse :bordered="false">
        <a-collapse-panel key="history" :header="t('annotator.historyAnnotations')">
          <div v-if="historyGroups.length === 0" class="empty-hint">
            {{ t('annotator.noAnnotations') }}
          </div>
          <div class="history-list">
            <div
              v-for="(group, gIdx) in historyGroups"
              :key="gIdx"
              class="history-item"
              @dblclick="emit('view-history', group)"
            >
              <div class="history-name">{{ group.name }}</div>
              <div class="history-count">{{ t('annotator.annotationCount', { count: group.annotations.length }) }}</div>
            </div>
          </div>
        </a-collapse-panel>
      </a-collapse>
    </div>
  </div>
</template>

<style scoped>
.annotation-sidebar {
  width: 280px;
  height: 100%;
  border-right: 1px solid #e8e8e8;
  overflow-y: auto;
  background: #fafafa;
  display: flex;
  flex-direction: column;
}

.sidebar-section {
  padding: 12px;
}

.sidebar-section-header {
  font-size: 14px;
  font-weight: 600;
  color: #333;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.empty-hint {
  font-size: 12px;
  color: #999;
  text-align: center;
  padding: 16px 0;
}

.annotation-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 50vh;
  overflow-y: auto;
}

.annotation-item {
  background: #fff;
  border: 1px solid #e8e8e8;
  border-radius: 6px;
  padding: 8px 10px;
  cursor: pointer;
  transition: border-color 0.2s;
}

.annotation-item:hover {
  border-color: #bbb;
}

.annotation-item-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 4px;
}

.annotation-index {
  font-size: 12px;
  font-weight: 600;
  color: #e53935;
}

.annotation-line {
  font-size: 11px;
  color: #aaa;
}

.annotation-item-body {
  font-size: 12px;
  color: #555;
  line-height: 1.4;
  margin-bottom: 6px;
}

.annotation-item-actions {
  display: flex;
  gap: 2px;
}

.annotation-item-actions :deep(.ant-btn-link) {
  font-size: 11px;
  padding: 0 4px;
  height: auto;
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.history-item {
  padding: 8px 10px;
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.15s;
  border: 1px solid transparent;
}

.history-item:hover {
  background: #f0f0f0;
  border-color: #ddd;
}

.history-name {
  font-size: 12px;
  color: #333;
  margin-bottom: 2px;
}

.history-count {
  font-size: 11px;
  color: #999;
}
</style>
