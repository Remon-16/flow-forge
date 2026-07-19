<script setup lang="ts">
import { computed, ref, onMounted, onUpdated, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import MarkdownIt from 'markdown-it'
import mermaid from 'mermaid'
import type { PlanSections } from '@flow-forge-schemas'

export interface AnnotationData {
  line_number: number
  selected_text: string
  review_comment: string
  chunk_id?: string  // 所属 chunk_id / owning chunk identifier
}

const props = defineProps<{
  planContent: string
  annotations: AnnotationData[]
  showLineNumbers?: boolean
  /** plan_sections.json 数据，用于 chunk_id 关联 / plan_sections.json data for chunk_id association */
  sections?: PlanSections | null
}>()

const emit = defineEmits<{
  'add-annotation': [selectedText: string, lineNumber: number, chunkId?: string]
  'edit-annotation': [index: number]
  'delete-annotation': [index: number]
}>()

const { t } = useI18n()
const previewRef = ref<HTMLElement | null>(null)
const contextMenuVisible = ref(false)
const contextMenuX = ref(0)
const contextMenuY = ref(0)
const selectedText = ref('')
const selectedLineNumber = ref(0)

// Annotation popover state
const annotationPopoverVisible = ref(false)
const activeAnnotationIdx = ref(-1)
const popoverAnchorStyle = ref<Record<string, string>>({})

const activeAnnotation = computed(() => {
  if (activeAnnotationIdx.value < 0 || activeAnnotationIdx.value >= props.annotations.length) return null
  return props.annotations[activeAnnotationIdx.value]
})

const md = new MarkdownIt({ html: true, breaks: true })

// --- Mermaid initialization ---
mermaid.initialize({ startOnLoad: false, theme: 'default' })

// Custom fence renderer for mermaid blocks
const defaultFence = md.renderer.rules.fence!
md.renderer.rules.fence = (tokens, idx, options, env, self) => {
  const token = tokens[idx]
  const lang = token.info.trim()
  if (lang === 'mermaid') {
    return `<pre class="mermaid">${token.content}</pre>`
  }
  return defaultFence(tokens, idx, options, env, self)
}

// --- Block-level rendering with data-source-line ---
interface MarkdownBlock {
  startLine: number
  content: string
}

function splitIntoBlocks(markdown: string): MarkdownBlock[] {
  const lines = markdown.split('\n')
  const blocks: MarkdownBlock[] = []
  let currentBlock: string[] = []
  let currentStart = 1
  let insideFence = false

  for (let i = 0; i < lines.length; i++) {
    const lineNum = i + 1
    const trimmed = lines[i].trim()

    // Detect fence open/close: a line starting with ``` or ~~~
    const isFenceMarker = /^(`{3,}|~{3,})/.test(trimmed)

    if (isFenceMarker) {
      if (!insideFence) {
        // Opening fence: flush any preceding block, start fenced block
        if (currentBlock.length > 0) {
          blocks.push({ startLine: currentStart, content: currentBlock.join('\n') })
          currentBlock = []
        }
        currentStart = lineNum
        insideFence = true
      } else {
        // Closing fence: add this line and flush
        currentBlock.push(lines[i])
        blocks.push({ startLine: currentStart, content: currentBlock.join('\n') })
        currentBlock = []
        currentStart = lineNum + 1
        insideFence = false
        continue
      }
    }

    if (insideFence) {
      if (currentBlock.length === 0) currentStart = lineNum
      currentBlock.push(lines[i])
    } else if (trimmed === '') {
      if (currentBlock.length > 0) {
        blocks.push({ startLine: currentStart, content: currentBlock.join('\n') })
        currentBlock = []
      }
      currentStart = lineNum + 1
    } else {
      if (currentBlock.length === 0) currentStart = lineNum
      currentBlock.push(lines[i])
    }
  }
  if (currentBlock.length > 0) {
    blocks.push({ startLine: currentStart, content: currentBlock.join('\n') })
  }
  return blocks
}

function applyAnnotationHighlights(html: string, annotations: AnnotationData[]): string {
  if (annotations.length === 0) return html

  // Sort by text length descending: longer matches first to avoid substring conflicts
  const sorted = annotations
    .map((ann, i) => ({ ann, idx: i }))
    .sort((a, b) => b.ann.selected_text.length - a.ann.selected_text.length)

  const parser = new DOMParser()
  const doc = parser.parseFromString(html, 'text/html')

  for (const { ann, idx } of sorted) {
    const searchText = ann.selected_text
    if (!searchText) continue

    const walker = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT)
    let found = false

    while (walker.nextNode() && !found) {
      const node = walker.currentNode as Text
      if (node.parentElement?.closest('mark.annotated')) continue

      const text = node.textContent || ''
      const pos = text.indexOf(searchText)
      if (pos === -1) continue

      // Split: [before] [match] [after]
      const afterNode = node.splitText(pos + searchText.length)
      const matchNode = node.splitText(pos)

      const mark = doc.createElement('mark')
      mark.className = 'annotated'
      mark.setAttribute('data-annotation-id', String(idx))

      const badge = doc.createElement('sup')
      badge.className = 'annotation-badge'
      badge.textContent = String(idx + 1)

      const parent = node.parentElement!
      parent.insertBefore(mark, afterNode)
      mark.appendChild(matchNode)
      mark.appendChild(badge)

      found = true
    }
  }

  return doc.body.innerHTML
}

const renderedHtml = computed(() => {
  // 先提取 chunk 边界标记 / Extract chunk boundary markers first
  let markdown = props.planContent
  const chunkMarkers: { line: number; chunkId: string }[] = []
  const markerRegex = /<!--\s*chunk:(\S+)\s*-->/g
  let m: RegExpExecArray | null
  while ((m = markerRegex.exec(markdown)) !== null) {
    const lineNum = markdown.substring(0, m.index).split('\n').length
    chunkMarkers.push({ line: lineNum, chunkId: m[1] })
  }
  // 去除标记，避免渲染到 HTML 中 / Remove markers to avoid rendering
  markdown = markdown.replace(markerRegex, '')

  const blocks = splitIntoBlocks(markdown)
  const markerMap = new Map<number, string>()
  for (const mk of chunkMarkers) {
    markerMap.set(mk.line, mk.chunkId)
  }

  // 找到每个 block 所属的 chunk / Find which chunk each block belongs to
  let currentChunkId = ''
  const sortedMarkers = chunkMarkers.sort((a, b) => a.line - b.line)

  let html = blocks.map(block => {
    if (!block.content) return ''
    // 更新当前 chunk_id / Update current chunk_id
    for (const mk of sortedMarkers) {
      if (mk.line <= block.startLine) {
        currentChunkId = mk.chunkId
      }
    }
    const rendered = md.render(block.content)
    const chunkAttr = currentChunkId ? ` data-chunk-id="${currentChunkId}"` : ''
    const chunkLabel = currentChunkId && props.showLineNumbers
      ? `<span class="chunk-label" title="${currentChunkId}">${currentChunkId}</span>`
      : ''
    return `<div data-source-line="${block.startLine}"${chunkAttr} class="md-block">${chunkLabel}${rendered}</div>`
  }).join('\n')

  html = applyAnnotationHighlights(html, props.annotations)
  return html
})

// Mermaid rendering
async function renderMermaid() {
  await nextTick()
  const el = previewRef.value
  if (!el) return
  const els = el.querySelectorAll<HTMLElement>('.mermaid')
  if (els.length === 0) return

  for (const mel of els) {
    if (mel.getAttribute('data-processed') === 'true') continue
    try {
      mel.removeAttribute('data-processed')
      if (!mel.textContent) continue
      mel.innerHTML = mel.textContent
    } catch { /* ignore */ }
  }
  try {
    await mermaid.run({ nodes: Array.from(els) })
  } catch { /* mermaid rendering errors are non-fatal */ }
}

watch(() => props.planContent, () => {
  nextTick(() => renderMermaid())
})

onMounted(() => renderMermaid())
onUpdated(() => renderMermaid())

// --- DOM-based line number detection ---
function findLineNumber(): number {
  const selection = window.getSelection()
  if (!selection || !selection.anchorNode) return 0

  let node: Node | null = selection.anchorNode
  while (node && node !== previewRef.value) {
    if (node instanceof HTMLElement) {
      const line = node.dataset.sourceLine
      if (line) return parseInt(line, 10)
    }
    node = node.parentNode
  }
  return 0
}

// 根据 selected_text 查找所属 chunk_id / Find chunk_id by selected_text
function findChunkId(text: string): string | undefined {
  if (!props.sections || !text) return undefined
  // 在 business_understanding 中 / In business_understanding
  if (props.sections.business_understanding?.includes(text)) return '__global__'
  // 在 single_api 和 biz_flows 中查找 / Search in single_api and biz_flows
  for (const sec of [...(props.sections.single_api || []), ...(props.sections.biz_flows || [])]) {
    if (sec.content?.includes(text)) return sec.chunk_id
  }
  return undefined
}

// --- Context menu ---
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
  selectedLineNumber.value = findLineNumber()
  contextMenuX.value = e.clientX
  contextMenuY.value = e.clientY
  contextMenuVisible.value = true
}

function handleAddAnnotation() {
  contextMenuVisible.value = false
  const chunkId = findChunkId(selectedText.value)
  emit('add-annotation', selectedText.value, selectedLineNumber.value, chunkId)
}

function onMarkdownClick(e: MouseEvent) {
  const target = e.target as HTMLElement
  const mark = target.closest('mark.annotated') as HTMLElement | null
  if (mark) {
    const idxStr = mark.dataset.annotationId
    if (idxStr !== undefined) {
      const idx = parseInt(idxStr, 10)
      if (!isNaN(idx) && props.annotations[idx]) {
        e.stopPropagation()
        openAnnotationPopover(idx, mark)
        return
      }
    }
  }
  annotationPopoverVisible.value = false
  contextMenuVisible.value = false
}

function openAnnotationPopover(idx: number, markEl: HTMLElement) {
  const container = markEl.closest('.markdown-preview-container')
  if (!container) return
  const markRect = markEl.getBoundingClientRect()
  const containerRect = container.getBoundingClientRect()

  popoverAnchorStyle.value = {
    position: 'absolute',
    left: `${markRect.left - containerRect.left}px`,
    top: `${markRect.top - containerRect.top}px`,
    width: `${markRect.width}px`,
    height: `${markRect.height}px`,
    pointerEvents: 'none',
  }
  activeAnnotationIdx.value = idx
  annotationPopoverVisible.value = true
}

function handlePopoverEdit() {
  if (activeAnnotationIdx.value >= 0) {
    emit('edit-annotation', activeAnnotationIdx.value)
  }
  annotationPopoverVisible.value = false
}

function handlePopoverDelete() {
  if (activeAnnotationIdx.value >= 0) {
    emit('delete-annotation', activeAnnotationIdx.value)
  }
  annotationPopoverVisible.value = false
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
  <div class="markdown-preview-container">
    <div
      ref="previewRef"
      class="markdown-preview"
      :class="{ 'show-line-numbers': showLineNumbers }"
      v-html="renderedHtml"
      @contextmenu="onContextMenu"
      @click="onMarkdownClick"
    />

    <!-- Annotation click popover -->
    <a-popover
      v-model:open="annotationPopoverVisible"
      placement="top"
      :destroyTooltipOnHide="true"
    >
      <template #content>
        <div class="annotation-popover-body" v-if="activeAnnotation">
          <div class="popover-comment">{{ activeAnnotation.review_comment }}</div>
          <div class="popover-meta">L{{ activeAnnotation.line_number }}</div>
          <a-space style="margin-top: 10px;">
            <a-button size="small" type="primary" @click="handlePopoverEdit">
              {{ t('annotator.editAnnotation') }}
            </a-button>
            <a-button size="small" danger @click="handlePopoverDelete">
              {{ t('annotator.deleteAnnotation') }}
            </a-button>
          </a-space>
        </div>
      </template>
      <span class="annotation-popover-anchor" :style="popoverAnchorStyle" />
    </a-popover>
  </div>

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

.md-block {
  /* display: contents would break data-source-line traversal for some children */
  margin-bottom: 4px;
}

/* 行号栏：切换不改正文布局（零抖动）；开启时行号向左伸进预览区外侧的大留白 */
/* Line-number gutter: no layout shift on toggle; when on, numbers reach left into the outer whitespace */
/* 用 :deep() 穿透 v-html 注入的 .md-block（否则 scoped 选择器带 [data-v-*] 永不命中） */
/* Use :deep() to pierce the v-html-injected .md-block (scoped selectors carry [data-v-*] and never match otherwise) */
.markdown-preview.show-line-numbers :deep(.md-block) {
  position: relative;
}
.markdown-preview.show-line-numbers :deep(.md-block)::before {
  content: attr(data-source-line);
  position: absolute;
  left: -60px;      /* 负偏移伸进预览区外侧留白 / negative offset into the outer whitespace */
  width: 48px;      /* 宽裕区域，可容 4~6 位行号 / roomy, fits 4-6 digit line numbers */
  text-align: right;
  color: #999;      /* 比原 #bbb 略深、更清晰 / slightly darker than #bbb for legibility */
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
  line-height: inherit;
  user-select: none;
  pointer-events: none;
}

/* chunk_id 标签 / chunk_id label — 显示在每块第一行上方 */
.markdown-preview.show-line-numbers :deep(.chunk-label) {
  display: block;
  font-size: 11px;
  color: #1677ff;
  background: #e6f4ff;
  padding: 1px 8px;
  border-radius: 3px;
  margin-bottom: 2px;
  font-family: 'Consolas', 'Monaco', monospace;
  user-select: none;
  cursor: pointer;
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
  padding: 1px 3px;
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
  position: absolute;
  bottom: -6px;
  right: -6px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 16px;
  min-width: 16px;
  font-size: 10px;
  line-height: 1;
  color: #fff;
  background: #007ACC;
  border-radius: 8px;
  padding: 0 4px;
  cursor: pointer;
  z-index: 1;
}
@keyframes flash {
  0% { background: #ff9800; }
  100% { background: #fff3b0; }
}

/* Container for relative positioning context */
.markdown-preview-container {
  position: relative;
}

/* Invisible anchor for annotation popover */
.annotation-popover-anchor {
  display: block;
  pointer-events: none;
}

/* Popover body styles */
.annotation-popover-body {
  min-width: 200px;
  max-width: 340px;
}

.popover-comment {
  font-size: 13px;
  color: #333;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.popover-meta {
  font-size: 11px;
  color: #aaa;
  margin-top: 8px;
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
