<!-- 可复用批注器面板 / Reusable annotator panel.
     从 PlanAnnotatorView 提取，用于独立页面和内嵌 AgentView 两种场景。
     Extracted from PlanAnnotatorView for use in standalone page and embedded AgentView. -->

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { CaretLeftOutlined, CaretRightOutlined } from '@ant-design/icons-vue'
import MarkdownPreview from './MarkdownPreview.vue'
import AnnotationSidebar from './AnnotationSidebar.vue'
import AnnotationDialog from './AnnotationDialog.vue'
import type { AnnotationData } from './MarkdownPreview.vue'
import type { HistoryGroup } from './AnnotationSidebar.vue'
import HistoryAnnotationViewer from './HistoryAnnotationViewer.vue'
import ResizableDivider from '../layout/ResizableDivider.vue'
import { useSplitter } from '../../composables/useSplitter'
import { readFile, listDirectoryAll, exists, writeFile } from '../../utils/desktop-bridge'
import { useSettingsStore } from '../../stores/settings'
import { joinPath } from '../../utils/path-utils'
import type { PlanSections } from '@flow-forge-schemas'
import { assemblePlanMd } from '@flow-forge-schemas'

const { t } = useI18n()
const settings = useSettingsStore()

const props = defineProps<{
  /** 计划 sections 数据 (可选，如未提供则从 memoryDir/plan_sections.json 读取) */
  sections?: PlanSections
  /** memory_dir 路径 (用于加载 plan_sections.json + 保存/加载批注) */
  memoryDir: string
  /** 是否显示内嵌工具栏 */
  showToolbar?: boolean
  /** 左侧边栏默认可见性 / Default visibility for left sidebar */
  defaultSidebarVisible?: boolean
}>()

const emit = defineEmits<{
  updateAnnotations: [annotations: AnnotationData[]]
  annotationActivity: []
}>()

// 左侧边栏可见性 / Left sidebar visibility
const sidebarVisible = ref(props.defaultSidebarVisible !== false)

// 左侧边栏拖拽调整宽度 / Left sidebar resizable width
const leftSplitter = useSplitter({
  direction: 'vertical',
  defaultSize: 280,
  minSize: 180,
  maxSize: 500,
  reverse: false,
})

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

// 内联 chunk 编辑器状态 / Inline chunk editor state
const selectedChunkId = ref('')
const editorVisible = ref(false)
const editingContent = ref('')
const editingMermaid = ref('')

// 判断选中的 chunk 是否为 biz 类型 / Check if selected chunk is biz type
const selectedChunkIsBiz = computed(() => {
  if (!planSections.value || !selectedChunkId.value) return false
  return planSections.value.biz_flows?.some(s => s.chunk_id === selectedChunkId.value) || false
})

// 右侧编辑器拖拽调整宽度 / Right editor resizable width
const rightEditorSplitter = useSplitter({
  direction: 'vertical',
  defaultSize: 450,
  minSize: 300,
  maxSize: 900,
  reverse: true,
})

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

// 内联编辑器：点击 chunk block 打开编辑器 / Inline editor: open on chunk block click
function handleChunkClick(chunkId: string) {
  if (!planSections.value) return
  // 查找 chunk 数据 / Look up chunk data
  let chunk: { content: string; mermaid?: string } | null = null
  const apiSec = planSections.value.single_api?.find(s => s.chunk_id === chunkId)
  if (apiSec) {
    chunk = { content: apiSec.content || '', mermaid: undefined }
  } else {
    const bizSec = planSections.value.biz_flows?.find(s => s.chunk_id === chunkId)
    if (bizSec) {
      chunk = { content: bizSec.content || '', mermaid: bizSec.mermaid || '' }
    }
  }
  if (!chunk) return

  selectedChunkId.value = chunkId
  editingContent.value = chunk.content
  editingMermaid.value = chunk.mermaid || ''
  editorVisible.value = true
}

// 关闭编辑器 / Close editor
function closeEditor() {
  editorVisible.value = false
  selectedChunkId.value = ''
  editingContent.value = ''
  editingMermaid.value = ''
}

// 保存编辑器内容 / Save editor content
async function saveEditor() {
  if (!planSections.value || !selectedChunkId.value || !props.memoryDir) return
  // 更新 planSections / Update planSections
  const apiSec = planSections.value.single_api?.find(s => s.chunk_id === selectedChunkId.value)
  if (apiSec) {
    apiSec.content = editingContent.value
  } else {
    const bizSec = planSections.value.biz_flows?.find(s => s.chunk_id === selectedChunkId.value)
    if (bizSec) {
      bizSec.content = editingContent.value
      bizSec.mermaid = editingMermaid.value
    }
  }
  // 重新组装 planContent 刷新预览 / Reassemble planContent to refresh preview
  planContent.value = assemblePlanMd(planSections.value)
  // 持久化到磁盘 / Persist to disk
  const sectionsPath = joinPath(props.memoryDir, 'plan_sections.json')
  try {
    await writeFile(sectionsPath, JSON.stringify(planSections.value, null, 2))
    message.success(t('annotator.autoSaved'))
  } catch (e: any) {
    message.error(e?.message || 'Failed to save plan sections')
  }
  closeEditor()
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
      <!-- 左侧边栏（可折叠 + 可拖拽宽度）/ Left sidebar (collapsible + resizable) -->
      <template v-if="sidebarVisible">
        <div class="sidebar-wrapper" :style="{ width: leftSplitter.size.value + 'px' }">
          <AnnotationSidebar
            :annotations="annotations"
            :history-groups="historyGroups"
            @edit="handleEditAnnotation"
            @delete="handleDeleteAnnotation"
            @scroll-to="handleScrollTo"
            @view-history="handleViewHistory"
          />
        </div>
        <ResizableDivider
          orientation="vertical"
          @mousedown="leftSplitter.onDividerMousedown"
        />
      </template>
      <!-- 边栏折叠按钮 / Sidebar toggle button -->
      <div class="sidebar-toggle" @click="sidebarVisible = !sidebarVisible" :title="sidebarVisible ? t('annotator.closeSidebar') : t('annotator.openSidebar')">
        <CaretLeftOutlined v-if="sidebarVisible" />
        <CaretRightOutlined v-else />
      </div>
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
          @chunk-click="handleChunkClick"
        />
        <div v-if="autoSaveStatus" class="autosave-indicator">{{ autoSaveStatus }}</div>
      </div>

      <!-- 右侧内联 Chunk 编辑器 / Right inline chunk editor -->
      <template v-if="editorVisible && selectedChunkId">
        <ResizableDivider
          orientation="vertical"
          @mousedown="rightEditorSplitter.onDividerMousedown"
        />
        <div class="chunk-editor-panel" :style="{ width: rightEditorSplitter.size.value + 'px' }">
          <div class="chunk-editor-header">
            <span class="chunk-editor-title">{{ t('annotator.editChunk') }}: {{ selectedChunkId }}</span>
            <a-button size="small" type="text" @click="closeEditor">✕</a-button>
          </div>
          <div class="chunk-editor-body">
            <label>{{ t('annotator.content') }} (Markdown)</label>
            <a-textarea v-model:value="editingContent" :rows="12" />
            <template v-if="selectedChunkIsBiz">
              <label style="margin-top: 16px;">{{ t('annotator.mermaid') }}</label>
              <a-textarea v-model:value="editingMermaid" :rows="8" style="font-family: monospace;" />
            </template>
          </div>
          <div class="chunk-editor-footer">
            <a-button size="small" @click="closeEditor">{{ t('annotator.cancel') }}</a-button>
            <a-button size="small" type="primary" @click="saveEditor">{{ t('annotator.save') }}</a-button>
          </div>
        </div>
      </template>
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
  flex: 1;           /* 撑满父级 flex 容器 / fill parent flex container */
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
.sidebar-wrapper {
  flex-shrink: 0;
  overflow: hidden;
}
.sidebar-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;              /* 加宽，更容易点击 / wider for easier click */
  cursor: pointer;
  background: #f0f0f0;      /* 略微区别于预览区 / slightly different from preview */
  border-left: 1px solid #d9d9d9;
  border-right: 1px solid #d9d9d9;
  color: #666;              /* 更高对比度 / higher contrast */
  font-size: 14px;          /* 图标更大 / larger icon */
  user-select: none;
  flex-shrink: 0;
  transition: background 0.15s, color 0.15s;
}
.sidebar-toggle:hover {
  background: #e6f4ff;
  color: #1677ff;
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

/* 内联 Chunk 编辑器 / Inline chunk editor */
.chunk-editor-panel {
  flex-shrink: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  border-left: 1px solid #e8e8e8;
  background: #fafafa;
}
.chunk-editor-header {
  padding: 8px 12px;
  border-bottom: 1px solid #e8e8e8;
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
  font-size: 13px;
  flex-shrink: 0;
}
.chunk-editor-body {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
}
.chunk-editor-body label {
  display: block;
  font-weight: 600;
  font-size: 12px;
  color: #333;
  margin-bottom: 4px;
}
.chunk-editor-footer {
  padding: 8px 12px;
  border-top: 1px solid #e8e8e8;
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  flex-shrink: 0;
}
</style>
