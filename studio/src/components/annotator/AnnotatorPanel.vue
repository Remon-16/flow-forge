<!-- 可复用批注器面板 / Reusable annotator panel.
     从 PlanAnnotatorView 提取，用于独立页面和内嵌 AgentView 两种场景。
     Extracted from PlanAnnotatorView for use in standalone page and embedded AgentView. -->

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import MarkdownPreview from './MarkdownPreview.vue'
import AnnotationSidebar from './AnnotationSidebar.vue'
import AnnotationDialog from './AnnotationDialog.vue'
import type { AnnotationData } from './MarkdownPreview.vue'
import type { HistoryGroup } from './AnnotationSidebar.vue'
import HistoryAnnotationViewer from './HistoryAnnotationViewer.vue'
import { readFile, listDirectoryAll, exists, writeFile } from '../../utils/desktop-bridge'
import { useSettingsStore } from '../../stores/settings'
import { joinPath } from '../../utils/path-utils'
import type { PlanSections } from '../../types/agent'
import { assemblePlanMd } from '../../types/agent'

const { t } = useI18n()
const settings = useSettingsStore()

const props = defineProps<{
  /** 计划 sections 数据 (可选，如未提供则从 memoryDir/plan_sections.json 读取) */
  sections?: PlanSections
  /** memory_dir 路径 (用于加载 plan_sections.json + 保存/加载批注) */
  memoryDir: string
  /** 是否显示内嵌工具栏 */
  showToolbar?: boolean
}>()

const emit = defineEmits<{
  updateAnnotations: [annotations: AnnotationData[]]
  annotationActivity: []
}>()

// 计划内容和 sections / Plan content and sections
const planContent = ref('')
const planSections = ref<PlanSections | null>(props.sections || null)
const annotations = ref<AnnotationData[]>([])
const historyGroups = ref<HistoryGroup[]>([])
const autoSaveStatus = ref('')
let saveTimer: ReturnType<typeof setTimeout> | null = null

// Dialog state
const dialogVisible = ref(false)
const editingIndex = ref(-1)
const dialogSelectedText = ref('')
const dialogLineNumber = ref(0)
const dialogExistingComment = ref('')

// History viewer state
const historyViewerVisible = ref(false)
const historyViewerFile = ref('')
const historyViewerAnnotations = ref<AnnotationData[]>([])

// MarkdownPreview ref for scrolling
const previewRef = ref<InstanceType<typeof MarkdownPreview> | null>(null)

const zoomPercent = computed(() => Math.round(settings.zoom * 100) + '%')

const commentsPath = computed(() => {
  if (!props.memoryDir) return ''
  return joinPath(props.memoryDir, 'plan_comments.json')
})

// 从 plan_sections.json 加载 / Load from plan_sections.json
watch(() => props.memoryDir, async (dir) => {
  if (!dir) return
  // 加载 plan_sections.json 并组装 markdown 展示
  // Load plan_sections.json and assemble markdown for display
  if (!props.sections) {
    const sectionsPath = joinPath(dir, 'plan_sections.json')
    if (await exists(sectionsPath)) {
      try {
        const raw = await readFile(sectionsPath)
        const loaded = JSON.parse(raw) as PlanSections
        planSections.value = loaded
        planContent.value = assemblePlanMd(loaded)
      } catch { planContent.value = '' }
    }
  } else {
    planSections.value = props.sections
    planContent.value = assemblePlanMd(props.sections)
  }
  // 加载已有批注 / Load existing annotations
  const cp = joinPath(dir, 'plan_comments.json')
  if (await exists(cp)) {
    try {
      const raw = await readFile(cp)
      annotations.value = JSON.parse(raw)
    } catch { annotations.value = [] }
  } else {
    annotations.value = []
  }
  // Load history
  await loadHistory(dir)
}, { immediate: true })

async function loadHistory(dir: string) {
  const histDir = joinPath(dir, 'history-comments')
  if (!(await exists(histDir))) {
    historyGroups.value = []
    return
  }
  try {
    const entries = await listDirectoryAll(histDir)
    const groups: HistoryGroup[] = []
    if (Array.isArray(entries)) {
      for (const entry of entries) {
        if (entry.name.endsWith('.json') && !entry.isDirectory) {
          try {
            const raw = await readFile(entry.path)
            const anns = JSON.parse(raw)
            if (Array.isArray(anns)) {
              groups.push({ name: entry.name, path: entry.path, annotations: anns })
            }
          } catch { /* skip */ }
        }
      }
    }
    groups.sort((a, b) => b.name.localeCompare(a.name))
    historyGroups.value = groups
  } catch { historyGroups.value = [] }
}

// Auto-save on annotation changes (500ms debounce)
watch(annotations, () => {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(async () => {
    if (!commentsPath.value) return
    try {
      await writeFile(commentsPath.value, JSON.stringify(annotations.value, null, 2))
      autoSaveStatus.value = t('annotator.autoSaved')
      setTimeout(() => { autoSaveStatus.value = '' }, 2000)
    } catch (e: any) {
      message.error(e?.message || 'Auto-save failed')
    }
    emit('updateAnnotations', annotations.value)
  }, 500)
}, { deep: true })

// 批注操作 / Annotation actions
const dialogChunkId = ref('')

function handleAddAnnotation(selectedText: string, lineNumber: number, chunkId?: string) {
  dialogSelectedText.value = selectedText
  dialogLineNumber.value = lineNumber
  dialogChunkId.value = chunkId || ''
  dialogExistingComment.value = ''
  editingIndex.value = -1
  dialogVisible.value = true
  emit('annotationActivity')
}

function handleEditAnnotation(idx: number) {
  const ann = annotations.value[idx]
  if (!ann) return
  dialogSelectedText.value = ann.selected_text
  dialogLineNumber.value = ann.line_number
  dialogExistingComment.value = ann.review_comment
  editingIndex.value = idx
  dialogVisible.value = true
}

function handleDeleteAnnotation(idx: number) {
  annotations.value.splice(idx, 1)
}

function handleDialogSave(data: AnnotationData) {
  // 设置 chunk_id / Set chunk_id
  if (dialogChunkId.value) {
    data.chunk_id = dialogChunkId.value
  }
  if (editingIndex.value >= 0) {
    annotations.value[editingIndex.value] = data
  } else {
    annotations.value.push(data)
  }
  dialogVisible.value = false
  dialogChunkId.value = ''
}

function handleDialogClose() {
  dialogVisible.value = false
}

function handleScrollTo(idx: number) {
  previewRef.value?.scrollToAnnotation(idx)
}

function handleViewHistory(group: HistoryGroup) {
  historyViewerFile.value = group.name
  historyViewerAnnotations.value = group.annotations
  historyViewerVisible.value = true
}

// 控制器 / Controls
function zoomIn() { settings.zoomIn() }
function zoomOut() { settings.zoomOut() }
function zoomReset() { settings.zoomReset() }
function onPreviewWheel(e: WheelEvent) {
  if (e.ctrlKey) {
    e.preventDefault()
    if (e.deltaY < 0) settings.zoomIn()
    else if (e.deltaY > 0) settings.zoomOut()
  }
}
</script>

<template>
  <div class="annotator-panel">
    <!-- 内嵌工具栏 (可选) / Embedded toolbar (optional) -->
    <div v-if="showToolbar" class="annotator-mini-toolbar">
      <a-button size="small" @click="zoomOut" :disabled="settings.zoom <= 0.5" title="Ctrl+-">−</a-button>
      <span class="zoom-label">{{ zoomPercent }}</span>
      <a-button size="small" @click="zoomIn" :disabled="settings.zoom >= 2.0" title="Ctrl+=">+</a-button>
      <a-button size="small" @click="zoomReset" :disabled="settings.zoom === 1" title="Ctrl+0">⟲</a-button>
      <a-button
        size="small"
        :type="settings.showLineNumbers ? 'primary' : 'default'"
        @click="settings.toggleLineNumbers()"
      >
        {{ t('annotator.lineNumbers') }}
      </a-button>
    </div>

    <!-- 主内容 / Main content -->
    <div class="annotator-main" @wheel="onPreviewWheel">
      <AnnotationSidebar
        :annotations="annotations"
        :history-groups="historyGroups"
        @edit="handleEditAnnotation"
        @delete="handleDeleteAnnotation"
        @scroll-to="handleScrollTo"
        @view-history="handleViewHistory"
      />
      <div class="annotator-preview-wrapper" :style="{ zoom: settings.zoom }">
        <MarkdownPreview
          ref="previewRef"
          :plan-content="planContent"
          :annotations="annotations"
          :show-line-numbers="settings.showLineNumbers"
          :sections="planSections"
          @add-annotation="handleAddAnnotation"
          @edit-annotation="handleEditAnnotation"
          @delete-annotation="handleDeleteAnnotation"
        />
        <div v-if="autoSaveStatus" class="autosave-indicator">{{ autoSaveStatus }}</div>
      </div>
    </div>

    <!-- Annotation Dialog -->
    <AnnotationDialog
      :visible="dialogVisible"
      :selected-text="dialogSelectedText"
      :line-number="dialogLineNumber"
      :existing-comment="dialogExistingComment"
      @save="handleDialogSave"
      @close="handleDialogClose"
    />

    <!-- History Viewer -->
    <HistoryAnnotationViewer
      :visible="historyViewerVisible"
      :file-name="historyViewerFile"
      :annotations="historyViewerAnnotations"
      @close="historyViewerVisible = false"
    />
  </div>
</template>

<style scoped>
.annotator-panel {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  height: 100%;
}
.annotator-mini-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  border-bottom: 1px solid #e8e8e8;
  background: #fafafa;
  flex-shrink: 0;
  font-size: 12px;
}
.zoom-label {
  font-size: 12px;
  min-width: 36px;
  text-align: center;
  color: #666;
  user-select: none;
}
.annotator-main {
  flex: 1;
  display: flex;
  overflow: hidden;
  min-height: 0;
}
.annotator-preview-wrapper {
  flex: 1;
  overflow-y: auto;
  background: #fff;
  position: relative;
}
.autosave-indicator {
  position: absolute;
  bottom: 8px;
  right: 16px;
  font-size: 11px;
  color: #52c41a;
  background: #f6ffed;
  padding: 2px 8px;
  border-radius: 4px;
  border: 1px solid #b7eb8f;
}
</style>
