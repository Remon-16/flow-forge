<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import type { AnnotationData } from '../annotator/MarkdownPreview.vue'
import { readFile, exists, writeFile } from '../../utils/desktop-bridge'

const { t } = useI18n()

const props = defineProps<{
  memoryDir: string
}>()

const emit = defineEmits<{
  annotationActivity: []
}>()

// State
const planContent = ref('')
const annotations = ref<AnnotationData[]>([])
const loading = ref(false)

// 自动保存 / Auto-save
const autoSaveStatus = ref('')
let saveTimer: ReturnType<typeof setTimeout> | null = null

const commentsPath = computed(() => {
  if (!props.memoryDir) return ''
  return props.memoryDir.replace(/[/\\]$/, '') + '/plan_comments.json'
})

const planPath = computed(() => {
  if (!props.memoryDir) return ''
  return props.memoryDir.replace(/[/\\]$/, '') + '/plan.md'
})

// 加载计划内容 / Load plan content
watch(
  () => props.memoryDir,
  async (dir) => {
    if (!dir) return
    loading.value = true
    try {
      const p = planPath.value
      if (await exists(p)) {
        planContent.value = await readFile(p)
      }
      const c = commentsPath.value
      if (await exists(c)) {
        const raw = await readFile(c)
        try {
          annotations.value = JSON.parse(raw)
        } catch { annotations.value = [] }
      }
    } catch { /* ignore load errors */ }
    loading.value = false
  },
  { immediate: true },
)

// 批注变更时自动保存到磁盘（500ms debounce） / Auto-save annotations to disk on change (500ms debounce)
watch(annotations, () => {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(async () => {
    if (!commentsPath.value) return
    try {
      await writeFile(commentsPath.value, JSON.stringify(annotations.value, null, 2))
      autoSaveStatus.value = '✓'
      setTimeout(() => { autoSaveStatus.value = '' }, 1500)
    } catch (e: any) {
      message.error(e?.message || 'Failed to save annotations')
    }
  }, 500)
}, { deep: true })

// 添加批注 / Add annotation
function handleAddAnnotation(selectedText: string, lineNumber: number) {
  annotations.value.push({
    line_number: lineNumber,
    selected_text: selectedText,
    review_comment: '',
  })
  emit('annotationActivity')
}

// 编辑批注 / Edit annotation
function handleEditAnnotation(idx: number) {
  const ann = annotations.value[idx]
  if (!ann) return
  const newComment = prompt('Edit comment:', ann.review_comment)
  if (newComment !== null) {
    ann.review_comment = newComment
    emit('annotationActivity')
  }
}

// 删除批注 / Delete annotation
function handleDeleteAnnotation(idx: number) {
  annotations.value.splice(idx, 1)
}
</script>

<template>
  <div class="plan-review-drawer">
    <div v-if="loading" class="drawer-loading">
      <a-spin size="small" /> Loading plan...
    </div>

    <div v-else-if="planContent" class="drawer-content">
      <!-- 计划预览 / Plan preview -->
      <div class="plan-preview" v-html="planContent" />

      <!-- 批注列表 / Annotations list -->
      <div class="annotation-list">
        <div class="annotation-list-header">
          {{ t('annotator.currentAnnotations') }} ({{ annotations.length }})
          <span v-if="autoSaveStatus" class="auto-save-indicator">{{ autoSaveStatus }}</span>
        </div>
        <div
          v-for="(ann, i) in annotations"
          :key="i"
          class="annotation-item"
        >
          <span class="ann-idx">#{{ i + 1 }}</span>
          <span class="ann-line">L{{ ann.line_number }}</span>
          <span class="ann-text">{{ ann.selected_text?.slice(0, 40) }}</span>
          <a-button size="small" type="text" @click="handleEditAnnotation(i)">✏</a-button>
          <a-button size="small" type="text" danger @click="handleDeleteAnnotation(i)">✕</a-button>
        </div>
        <div v-if="annotations.length === 0" class="no-annotations">
          Select text in the plan preview to add annotations
        </div>
      </div>
    </div>

    <div v-else-if="!loading" class="drawer-empty">
      Plan not found at {{ planPath }}
    </div>
  </div>
</template>

<style scoped>
.plan-review-drawer {
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  margin-top: 12px;
  max-height: 400px;
  overflow-y: auto;
  background: #fff;
}
.drawer-loading, .drawer-empty {
  padding: 24px;
  text-align: center;
  color: #999;
}
.drawer-content {
  display: flex;
  max-height: 400px;
}
.plan-preview {
  flex: 1;
  padding: 16px;
  overflow-y: auto;
  font-size: 13px;
  line-height: 1.6;
  border-right: 1px solid #f0f0f0;
}
.annotation-list {
  width: 220px;
  min-width: 220px;
  padding: 8px;
  overflow-y: auto;
  font-size: 12px;
}
.annotation-list-header {
  font-weight: 600;
  margin-bottom: 8px;
  padding-bottom: 4px;
  border-bottom: 1px solid #f0f0f0;
}
.annotation-item {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px;
  background: #fffbe6;
  border-radius: 4px;
  margin-bottom: 4px;
}
.ann-idx { color: #999; }
.ann-line { color: #1677ff; }
.ann-text { flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.no-annotations { color: #999; font-style: italic; padding: 8px; }
.auto-save-indicator { color: #52c41a; font-size: 11px; margin-left: 4px; }
</style>
