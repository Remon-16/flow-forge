<script setup lang="ts">
import { ref, watch, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import MarkdownPreview from '../components/annotator/MarkdownPreview.vue'
import AnnotationSidebar from '../components/annotator/AnnotationSidebar.vue'
import AnnotationDialog from '../components/annotator/AnnotationDialog.vue'
import type { AnnotationData } from '../components/annotator/MarkdownPreview.vue'
import type { HistoryGroup } from '../components/annotator/AnnotationSidebar.vue'
import HistoryAnnotationViewer from '../components/annotator/HistoryAnnotationViewer.vue'
import { openDirectoryDialog, readFile, listDirectoryAll, exists, writeFile, isDesktop } from '../utils/desktop-bridge'
import { useSettingsStore } from '../stores/settings'

const router = useRouter()
const { t } = useI18n()
const settings = useSettingsStore()

// State
const directoryPath = ref('')
const planContent = ref('')
const annotations = ref<AnnotationData[]>([])
const historyGroups = ref<HistoryGroup[]>([])
const loading = ref(false)
const autoSaveStatus = ref('')

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

// Debounce timer for auto-save
let saveTimer: ReturnType<typeof setTimeout> | null = null

const commentsPath = computed(() => {
  if (!directoryPath.value) return ''
  return directoryPath.value.replace(/[/\\]$/, '') + '/plan_comments.json'
})

const planPath = computed(() => {
  if (!directoryPath.value) return ''
  return directoryPath.value.replace(/[/\\]$/, '') + '/plan.md'
})

const historyDir = computed(() => {
  if (!directoryPath.value) return ''
  return directoryPath.value.replace(/[/\\]$/, '') + '/history-comments'
})

async function openDirectory() {
  if (!isDesktop) {
    message.warning('请在桌面应用中打开目录。')
    return
  }

  try {
    const dir = await openDirectoryDialog()
    if (!dir) return

    loading.value = true
    directoryPath.value = dir

    // Read plan.md
    const planMdPath = dir.replace(/[/\\]$/, '') + '/plan.md'
    if (!(await exists(planMdPath))) {
      message.error(t('annotator.noPlan'))
      loading.value = false
      return
    }

    planContent.value = await readFile(planMdPath)

    // Read existing annotations
    const commentsFile = dir.replace(/[/\\]$/, '') + '/plan_comments.json'
    if (await exists(commentsFile)) {
      try {
        const raw = await readFile(commentsFile)
        annotations.value = JSON.parse(raw)
      } catch {
        annotations.value = []
      }
    } else {
      annotations.value = []
    }

    // Load history
    await loadHistory(dir)
    loading.value = false
  } catch (e: any) {
    message.error(e?.message || 'Failed to open directory')
    loading.value = false
  }
}

async function loadHistory(dir: string) {
  const histDir = dir.replace(/[/\\]$/, '') + '/history-comments'
  if (!(await exists(histDir))) {
    historyGroups.value = []
    return
  }

  try {
    const entries = await listDirectoryAll(histDir)
    const groups: HistoryGroup[] = []

    // Filter for json files - use the FileEntry array
    if (Array.isArray(entries)) {
      for (const entry of entries) {
        if (entry.name.endsWith('.json') && !entry.isDirectory) {
          try {
            const raw = await readFile(entry.path)
            const anns = JSON.parse(raw)
            if (Array.isArray(anns)) {
              groups.push({
                name: entry.name,
                path: entry.path,
                annotations: anns,
              })
            }
          } catch {
            // Skip unreadable files
          }
        }
      }
    }

    // Sort by name descending (newest first)
    groups.sort((a, b) => b.name.localeCompare(a.name))
    historyGroups.value = groups
  } catch {
    historyGroups.value = []
  }
}

// Auto-save on annotation changes
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
  }, 500)
}, { deep: true })

// Annotation actions
function handleAddAnnotation(selectedText: string, lineNumber: number) {
  dialogSelectedText.value = selectedText
  dialogLineNumber.value = lineNumber
  dialogExistingComment.value = ''
  editingIndex.value = -1
  dialogVisible.value = true
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
  if (editingIndex.value >= 0) {
    annotations.value[editingIndex.value] = data
  } else {
    annotations.value.push(data)
  }
  dialogVisible.value = false
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

function handleLanguageChange(lang: string) {
  settings.setLanguage(lang as 'zh-CN' | 'en-US')
}

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

function goBack() {
  router.push('/')
}

// Close context menu on escape
function onKeyDown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    dialogVisible.value = false
    historyViewerVisible.value = false
  } else if (e.ctrlKey && (e.key === '=' || e.key === '+')) {
    e.preventDefault()
    settings.zoomIn()
  } else if (e.ctrlKey && e.key === '-') {
    e.preventDefault()
    settings.zoomOut()
  } else if (e.ctrlKey && e.key === '0') {
    e.preventDefault()
    settings.zoomReset()
  }
}

onMounted(() => window.addEventListener('keydown', onKeyDown))
onUnmounted(() => window.removeEventListener('keydown', onKeyDown))
</script>

<template>
  <div class="plan-annotator">
    <!-- Toolbar -->
    <div class="annotator-toolbar">
      <a-button @click="goBack" size="small">
        ← {{ t('header.backHome') }}
      </a-button>
      <span class="toolbar-title">{{ t('annotator.title') }}</span>

      <a-button size="small" @click="zoomOut" :disabled="settings.zoom <= 0.5" title="Ctrl+-">−</a-button>
      <span class="zoom-label">{{ zoomPercent }}</span>
      <a-button size="small" @click="zoomIn" :disabled="settings.zoom >= 2.0" title="Ctrl+=">+</a-button>
      <a-button size="small" @click="zoomReset" :disabled="settings.zoom === 1" title="Ctrl+0">⟲</a-button>

      <a-select
        :value="settings.language"
        size="small"
        style="width: 90px"
        @change="handleLanguageChange"
      >
        <a-select-option value="zh-CN">中文</a-select-option>
        <a-select-option value="en-US">English</a-select-option>
      </a-select>
      <a-button type="primary" size="small" @click="openDirectory">
        {{ t('annotator.openDir') }}
      </a-button>
    </div>

    <!-- Main content -->
    <div class="annotator-main">
      <!-- Loading state -->
      <div v-if="loading" class="annotator-loading">
        <a-spin size="large" />
      </div>

      <!-- Empty state -->
      <div v-else-if="!planContent" class="annotator-empty">
        <div class="empty-icon">📋</div>
        <div class="empty-text">{{ t('annotator.noPlan') }}</div>
        <a-button type="primary" @click="openDirectory">
          {{ t('annotator.openDir') }}
        </a-button>
      </div>

      <!-- Editor layout -->
      <template v-else>
        <AnnotationSidebar
          :annotations="annotations"
          :history-groups="historyGroups"
          @edit="handleEditAnnotation"
          @delete="handleDeleteAnnotation"
          @scroll-to="handleScrollTo"
          @view-history="handleViewHistory"
        />
        <div class="annotator-preview-wrapper" :style="{ zoom: settings.zoom }" @wheel="onPreviewWheel">
          <MarkdownPreview
            ref="previewRef"
            :plan-content="planContent"
            :annotations="annotations"
            @add-annotation="handleAddAnnotation"
            @edit-annotation="handleEditAnnotation"
            @delete-annotation="handleDeleteAnnotation"
          />
          <div v-if="autoSaveStatus" class="autosave-indicator">
            {{ autoSaveStatus }}
          </div>
          <div v-if="directoryPath" class="directory-info">
            {{ directoryPath }}plan.md
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
.plan-annotator {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.annotator-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  border-bottom: 1px solid #e8e8e8;
  background: #fff;
  flex-shrink: 0;
}

.toolbar-title {
  flex: 1;
  font-size: 14px;
  font-weight: 600;
  color: #333;
}

.zoom-label {
  font-size: 12px;
  min-width: 40px;
  text-align: center;
  color: #666;
  user-select: none;
}

.annotator-main {
  flex: 1;
  display: flex;
  overflow: hidden;
}

.annotator-loading {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.annotator-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
}

.empty-icon {
  font-size: 48px;
  opacity: 0.5;
}

.empty-text {
  font-size: 16px;
  color: #999;
}

.annotator-preview-wrapper {
  flex: 1;
  overflow-y: auto;
  background: #fff;
  position: relative;
}

.autosave-indicator {
  position: fixed;
  bottom: 36px;
  right: 24px;
  font-size: 12px;
  color: #52c41a;
  background: #f6ffed;
  padding: 4px 12px;
  border-radius: 4px;
  border: 1px solid #b7eb8f;
  z-index: 100;
}

.directory-info {
  position: fixed;
  bottom: 8px;
  right: 24px;
  font-size: 11px;
  color: #bbb;
  z-index: 100;
}
</style>
