<script setup lang="ts">
import { computed, ref, onMounted, onUpdated, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import MarkdownIt from 'markdown-it'
import mermaid from 'mermaid'
import type { PlanSections } from '@flow-forge-schemas'
import { SECTION_HEADINGS } from '@flow-forge-schemas'

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
  /** 语言代码，用于章节标题 / Language code for section headings */
  language?: string
}>()

const emit = defineEmits<{
  'add-annotation': [selectedText: string, lineNumber: number, chunkId?: string]
  'edit-annotation': [index: number]
  'delete-annotation': [index: number]
  /** 用户点击某个 chunk block 时发射 / Emitted when user clicks a chunk block */
  'chunk-click': [chunkId: string]
}>()

const { t } = useI18n()
const previewRef = ref<HTMLElement | null>(null)
const contextMenuVisible = ref(false)
const contextMenuX = ref(0)
const contextMenuY = ref(0)
const selectedText = ref('')
const selectedLineNumber = ref(0)
const selectedChunkId = ref<string | undefined>(undefined)  // 在 onContextMenu 中提前捕获，避免 selection 失效 / captured early in onContextMenu to avoid stale selection

// Annotation popover state
const annotationPopoverVisible = ref(false)
const activeAnnotationIdx = ref(-1)
const popoverAnchorStyle = ref<Record<string, string>>({})

const activeAnnotation = computed(() => {
  if (activeAnnotationIdx.value < 0 || activeAnnotationIdx.value >= props.annotations.length) return null
  return props.annotations[activeAnnotationIdx.value]
})

// html: false 防止内容中的 HTML 标签（如 <script>）被浏览器解释导致截断
// html: false prevents HTML tags in content (e.g. <script>) from being interpreted by the browser
const md = new MarkdownIt({ html: false, breaks: true })

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

/** 从 PlanSections 数据直接构建 block 列表并渲染。
 *  Build block list directly from PlanSections data and render.
 *  不再依赖 markdown 中的 <!-- chunk:XXX --> 标记和行号匹配，
 *  从根本上消除行号偏移导致的 chunk_id 错配问题。
 *  No longer depends on <!-- chunk:XXX --> markers and line-number matching,
 *  eliminating chunk_id misattribution caused by line offset. */
function renderFromSections(sections: PlanSections): string {
  interface ChunkBlock extends MarkdownBlock {
    chunkId: string
  }

  const allBlocks: ChunkBlock[] = []

  // 按顺序收集各 section 的 (文本, chunkId) 对 / Collect (text, chunkId) pairs per section in order
  // 使用配对方式替代计数器，避免空 section 导致索引错位
  // Using paired approach instead of counters to avoid index misalignment from empty sections
  interface SectionText {
    text: string
    chunkId: string
  }
  const sectionTexts: SectionText[] = []
  const lang = props.language || 'zh-CN'
  const h = SECTION_HEADINGS

  // 业务理解 / Business understanding
  const buSection = sections.business_understanding
  const buText = buSection?.content?.trim() || ''
  if (buText) {
    const heading = h.business_understanding?.[lang] || ''
    const fullText = heading ? heading + '\n\n' + buText : buText
    sectionTexts.push({ text: fullText, chunkId: buSection?.chunk_id || 'business_understanding' })
  }

  // 单接口测试（仅首个 section 前加标题）/ Single API (heading only before first section)
  let isFirstApi = true
  for (const sec of sections.single_api) {
    const c = sec.content?.trim()
    if (c) {
      let fullText = c
      if (isFirstApi) {
        const heading = h.single_api?.[lang] || ''
        if (heading) fullText = heading + '\n\n' + c
        isFirstApi = false
      }
      // 添加 fallback：优先 chunk_id，其次 key / Fallback: chunk_id first, then key
      sectionTexts.push({ text: fullText, chunkId: sec.chunk_id || sec.key || '' })
    }
  }

  // 业务链路测试（仅首个 section 前加标题，文本在前流程图在后）/ Biz flows (heading only before first, content before mermaid)
  let isFirstBiz = true
  for (const sec of sections.biz_flows) {
    const parts: string[] = []
    if (isFirstBiz) {
      const heading = h.biz_flows?.[lang] || ''
      if (heading) parts.push(heading)
      isFirstBiz = false
    }
    if (sec.content?.trim()) parts.push(sec.content.trim())
    if (sec.mermaid?.trim()) parts.push(sec.mermaid.trim())
    if (parts.length) {
      sectionTexts.push({ text: parts.join('\n\n'), chunkId: sec.chunk_id || sec.key || '' })
    }
  }

  // 对每个 section 文本独立 splitIntoBlocks，标记 chunk_id
  // Split each section independently, tag with chunk_id
  let cumulativeLine = 1

  for (const { text, chunkId } of sectionTexts) {
    const secBlocks = splitIntoBlocks(text)
    for (const b of secBlocks) {
      allBlocks.push({
        ...b,
        startLine: cumulativeLine + b.startLine - 1,
        chunkId,
      })
    }
    // 更新累积行号（包含 section 间分隔的 \n\n）/ Update cumulative line count (includes \n\n separator)
    cumulativeLine += text.split('\n').length + 2
  }

  // 渲染 blocks / Render blocks
  let prevChunkId = ''
  let html = allBlocks.map(block => {
    if (!block.content) return ''
    const rendered = md.render(block.content)
    const isFirst = block.chunkId !== prevChunkId
    prevChunkId = block.chunkId
    const chunkAttr = block.chunkId ? ` data-chunk-id="${block.chunkId}"` : ''
    const firstAttr = isFirst ? ' data-first-of-chunk="true"' : ''
    return `<div data-source-line="${block.startLine}"${chunkAttr}${firstAttr} class="md-block">${rendered}</div>`
  }).join('\n')

  return applyAnnotationHighlights(html, props.annotations)
}

/** 旧的 marker 解析方式，作为 sections 不可用时的兜底。
 *  Old marker-based parsing as fallback when sections is unavailable. */
function renderFromMarkers(markdown: string): string {
  const chunkMarkers: { line: number; chunkId: string }[] = []
  const markerRegex = /<!--\s*chunk:(\S+)\s*-->/g
  let m: RegExpExecArray | null
  while ((m = markerRegex.exec(markdown)) !== null) {
    const lineNum = markdown.substring(0, m.index).split('\n').length
    chunkMarkers.push({ line: lineNum, chunkId: m[1] })
  }
  markdown = markdown.replace(markerRegex, '')

  const blocks = splitIntoBlocks(markdown)
  let currentChunkId = ''
  const sortedMarkers = chunkMarkers.sort((a, b) => a.line - b.line)
  let prevChunkId = ''

  let html = blocks.map(block => {
    if (!block.content) return ''
    for (const mk of sortedMarkers) {
      if (mk.line <= block.startLine) {
        currentChunkId = mk.chunkId
      }
    }
    const rendered = md.render(block.content)
    const chunkAttr = currentChunkId ? ` data-chunk-id="${currentChunkId}"` : ''
    const isFirst = currentChunkId !== prevChunkId
    prevChunkId = currentChunkId
    const firstAttr = isFirst ? ' data-first-of-chunk="true"' : ''
    return `<div data-source-line="${block.startLine}"${chunkAttr}${firstAttr} class="md-block">${rendered}</div>`
  }).join('\n')

  return applyAnnotationHighlights(html, props.annotations)
}

const renderedHtml = computed(() => {
  if (props.sections) {
    return renderFromSections(props.sections)
  }
  // 兜底：使用旧的 marker 方式 / Fallback: old marker-based approach
  return renderFromMarkers(props.planContent)
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

/** 从 DOM 树中查找选中文本所属的 chunk_id。
 *  Find chunk_id from DOM tree by traversing from selection anchor.
 *  不再使用文本子串匹配，直接从渲染后的 block 元素获取 data-chunk-id。
 *  No longer uses substring matching; gets data-chunk-id directly from rendered blocks.
 *  与 findLineNumber() 使用相同的 DOM 遍历模式。
 *  Uses the same DOM traversal pattern as findLineNumber(). */
function findChunkId(): string | undefined {
  const selection = window.getSelection()
  if (!selection || !selection.anchorNode) return undefined
  let node: Node | null = selection.anchorNode
  while (node && node !== previewRef.value) {
    if (node instanceof Element) {      /* Element 同时兼容 HTMLElement 和 SVGElement / Element covers both HTMLElement and SVGElement */
      const chunkId = (node as HTMLElement).dataset?.chunkId
      if (chunkId) return chunkId  /* 跳过空字符串和 未设置属性 / skip empty string and unset */
    }
    node = node.parentNode
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
  // 在 selection 有效时立即捕获 chunk_id / Capture chunk_id immediately while selection is valid
  selectedChunkId.value = findChunkId()
  contextMenuX.value = e.clientX
  contextMenuY.value = e.clientY
  contextMenuVisible.value = true
}

function handleAddAnnotation() {
  contextMenuVisible.value = false
  // 使用 onContextMenu 中存储的 chunk_id，避免重新读取已失效的 selection
  // Use stored chunk_id from onContextMenu to avoid re-reading a stale selection
  emit('add-annotation', selectedText.value, selectedLineNumber.value, selectedChunkId.value)
  selectedChunkId.value = undefined  // 重置 / reset
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

/** 双击 md-block 打开右侧 chunk 编辑器。
 *  Double-click md-block to open right chunk editor.
 *  与单击不同，双击是更明确的 "编辑" 意图，避免浏览时误触发。
 *  Unlike single-click, double-click is a clearer "edit" intent, preventing accidental triggers. */
function onMarkdownDblClick(e: MouseEvent) {
  const target = e.target as HTMLElement
  // 双击批注标记时不触发 chunk 编辑 / Don't trigger chunk edit on annotation double-click
  if (target.closest('mark.annotated')) return
  const block = target.closest('.md-block') as HTMLElement | null
  if (block?.dataset?.chunkId) {
    emit('chunk-click', block.dataset.chunkId)
  }
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
      @dblclick="onMarkdownDblClick"
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

/* chunk_id 标签 — 贴纸风格，显示在行号右侧、正文左侧，仅每个 chunk 首块显示
   chunk_id label — sticker-style between line numbers and content, only on first block of each chunk */
.markdown-preview.show-line-numbers :deep(.md-block[data-first-of-chunk])::after {
  content: attr(data-chunk-id);
  position: absolute;
  left: -130px;        /* 行号栏左侧，不遮挡正文 / left of line-number gutter, no text overlap */
  text-align: right;   /* 右对齐，贴近行号栏 / right-align toward line numbers */
  top: 0;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 10px;
  color: #1677ff;
  background: #e6f4ff;
  padding: 0 6px;
  border-radius: 2px;
  line-height: 18px;
  user-select: none;
  pointer-events: none;
  white-space: nowrap;
  max-width: 100px;
  overflow: hidden;
  text-overflow: ellipsis;
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
