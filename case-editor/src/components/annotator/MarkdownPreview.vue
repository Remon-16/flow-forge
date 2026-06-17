<script setup lang="ts">
import { computed, ref, onMounted, onUpdated, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import MarkdownIt from 'markdown-it'

export interface AnnotationData {
  line_number: number
  selected_text: string
  review_comment: string
}

const props = defineProps<{
  planContent: string
  annotations: AnnotationData[]
}>()

const emit = defineEmits<{
  'add-annotation': [selectedText: string, lineNumber: number]
}>()

const { t } = useI18n()
const previewRef = ref<HTMLElement | null>(null)
const contextMenuVisible = ref(false)
const contextMenuX = ref(0)
const contextMenuY = ref(0)
const selectedText = ref('')
const selectedLineNumber = ref(0)

const md = new MarkdownIt({ html: true, breaks: true })

function findLineNumber(text: string): number {
  const content = props.planContent
  const idx = content.indexOf(text)
  if (idx === -1) return 0
  const before = content.substring(0, idx)
  return before.split('\n').length
}

function getHighlightedHtml(): string {
  let html = md.render(props.planContent)

  // Sort annotations by selected_text length desc to avoid partial replacements
  const sorted = [...props.annotations].sort((a, b) => b.selected_text.length - a.selected_text.length)

  sorted.forEach((ann, idx) => {
    // Escape special regex chars in selected_text
    const escaped = ann.selected_text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    const regex = new RegExp(`(${escaped})`, 'g')
    html = html.replace(regex, (match) => {
      return `<mark class="annotated" data-annotation-id="${idx}">${match}<sup class="annotation-badge">${idx + 1}</sup></mark>`
    })
  })

  return html
}

const renderedHtml = computed(() => getHighlightedHtml())

function onContextMenu(e: MouseEvent) {
  const selection = window.getSelection()
  if (!selection || selection.isCollapsed) {
    contextMenuVisible.value = false
    return
  }

  const text = selection.toString().trim()
  if (!text) {
    contextMenuVisible.value = false
    return
  }

  e.preventDefault()
  selectedText.value = text
  selectedLineNumber.value = findLineNumber(text)
  contextMenuX.value = e.clientX
  contextMenuY.value = e.clientY
  contextMenuVisible.value = true
}

function handleAddAnnotation() {
  contextMenuVisible.value = false
  emit('add-annotation', selectedText.value, selectedLineNumber.value)
}

function closeContextMenu() {
  contextMenuVisible.value = false
}

// Scroll to annotation when clicked from sidebar
function scrollToAnnotation(idx: number) {
  const el = previewRef.value?.querySelector(`mark[data-annotation-id="${idx}"]`)
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    el.classList.add('annotation-flash')
    setTimeout(() => el.classList.remove('annotation-flash'), 2000)
  }
}

defineExpose({ scrollToAnnotation })
</script>

<template>
  <div
    ref="previewRef"
    class="markdown-preview"
    v-html="renderedHtml"
    @contextmenu="onContextMenu"
    @click="closeContextMenu"
  />

  <!-- Right-click context menu -->
  <Teleport to="body">
    <div
      v-if="contextMenuVisible"
      class="context-menu"
      :style="{ left: contextMenuX + 'px', top: contextMenuY + 'px' }"
      @click.stop
    >
      <div class="context-menu-item" @click="handleAddAnnotation">
        {{ t('annotator.addAnnotation') }}
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.markdown-preview {
  padding: 24px 32px;
  line-height: 1.8;
  font-size: 14px;
  color: #333;
  max-width: 860px;
  margin: 0 auto;
  user-select: text;
  cursor: text;
}

/* Markdown rendered content styles */
.markdown-preview :deep(h1) { font-size: 24px; font-weight: 700; margin: 24px 0 16px; border-bottom: 1px solid #eee; padding-bottom: 8px; }
.markdown-preview :deep(h2) { font-size: 20px; font-weight: 600; margin: 20px 0 12px; }
.markdown-preview :deep(h3) { font-size: 16px; font-weight: 600; margin: 16px 0 8px; }
.markdown-preview :deep(h4) { font-size: 14px; font-weight: 600; margin: 12px 0 6px; }
.markdown-preview :deep(p) { margin: 8px 0; }
.markdown-preview :deep(ul), .markdown-preview :deep(ol) { padding-left: 24px; margin: 8px 0; }
.markdown-preview :deep(li) { margin: 4px 0; }
.markdown-preview :deep(code) {
  background: #f0f0f0;
  padding: 2px 6px;
  border-radius: 3px;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
}
.markdown-preview :deep(pre) {
  background: #f5f5f5;
  padding: 16px;
  border-radius: 6px;
  overflow-x: auto;
  margin: 12px 0;
}
.markdown-preview :deep(pre code) {
  background: none;
  padding: 0;
}
.markdown-preview :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 12px 0;
}
.markdown-preview :deep(th), .markdown-preview :deep(td) {
  border: 1px solid #ddd;
  padding: 8px 12px;
  text-align: left;
}
.markdown-preview :deep(th) {
  background: #f5f5f5;
  font-weight: 600;
}
.markdown-preview :deep(blockquote) {
  border-left: 4px solid #ddd;
  padding-left: 16px;
  margin: 12px 0;
  color: #666;
}

/* Annotation highlights */
.markdown-preview :deep(mark.annotated) {
  background: #fff3b0;
  padding: 1px 2px;
  border-radius: 2px;
  cursor: pointer;
  position: relative;
  transition: background 0.2s;
}
.markdown-preview :deep(mark.annotated:hover) {
  background: #ffe066;
}
.markdown-preview :deep(mark.annotated.annotation-flash) {
  background: #ff9800;
  animation: flash 2s ease-out;
}
.markdown-preview :deep(sup.annotation-badge) {
  font-size: 10px;
  color: #fff;
  background: #e53935;
  border-radius: 8px;
  padding: 0 4px;
  margin-left: 2px;
  vertical-align: super;
  line-height: 1;
  cursor: pointer;
}
@keyframes flash {
  0% { background: #ff9800; }
  100% { background: #fff3b0; }
}
</style>

<style>
/* Context menu - global styles (not scoped) */
.context-menu {
  position: fixed;
  z-index: 9999;
  background: #fff;
  border: 1px solid #ddd;
  border-radius: 6px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.12);
  padding: 4px 0;
  min-width: 140px;
}
.context-menu-item {
  padding: 8px 16px;
  cursor: pointer;
  font-size: 13px;
  color: #333;
  transition: background 0.15s;
}
.context-menu-item:hover {
  background: #f0f0f0;
}
</style>
