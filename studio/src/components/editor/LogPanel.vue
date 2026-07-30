<script setup lang="ts">
// LogPanel — 编辑器底部可折叠 CLI 日志面板。
// Collapsible CLI log panel at the bottom of editor views.
import { ref, computed, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { useExecutorStore } from '../../stores/executor'
import { useConverterStore } from '../../stores/converter'
import type { LogEntry } from '../../types/agent'
const { t } = useI18n()
const executor = useExecutorStore()
const converter = useConverterStore()

// 面板展开高度（可拖拽调整）/ Panel expanded height (draggable)
const panelSize = ref(220)

// 拖拽调整面板高度 / Drag to resize panel height
function onDragHandleMousedown(e: MouseEvent) {
  e.preventDefault()
  const startY = e.clientY
  const startSize = panelSize.value

  function onMouseMove(ev: MouseEvent) {
    const delta = startY - ev.clientY  // 向上拖 = 正 delta，面板变大 / drag up = positive delta, panel grows
    panelSize.value = Math.max(80, startSize + delta)
  }

  function onMouseUp() {
    document.removeEventListener('mousemove', onMouseMove)
    document.removeEventListener('mouseup', onMouseUp)
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
  }

  document.addEventListener('mousemove', onMouseMove)
  document.addEventListener('mouseup', onMouseUp)
  document.body.style.cursor = 'row-resize'
  document.body.style.userSelect = 'none'
}

const collapsed = ref(true)
const autoScroll = ref(true)
const activeTab = ref<'executor' | 'converter'>('executor')

// 最近一次执行器的会话 / Most recent executor session with logs
const latestExecutorSession = computed(() => {
  return executor.sortedSessions.find(s => s.logLines.length > 0) ?? null
})

// 最近一次转换器的会话 / Most recent converter session with logs
const latestConverterSession = computed(() => {
  return converter.sortedSessions.find(s => s.logLines.length > 0) ?? null
})

// 当前显示的日志 / Currently displayed logs
const displayLogs = computed((): LogEntry[] => {
  if (activeTab.value === 'executor') {
    return latestExecutorSession.value?.logLines ?? []
  }
  return latestConverterSession.value?.logLines ?? []
})

// 当前会话状态 / Current session status
const executorStatus = computed(() => latestExecutorSession.value?.status ?? null)
const converterStatus = computed(() => latestConverterSession.value?.status ?? null)

const hasLogs = computed(() => {
  return (latestExecutorSession.value && latestExecutorSession.value.logLines.length > 0)
    || (latestConverterSession.value && latestConverterSession.value.logLines.length > 0)
})

function toggleCollapse() {
  collapsed.value = !collapsed.value
}

const panelHeight = computed(() => collapsed.value ? '32px' : panelSize.value + 'px')

// 日志容器 DOM 引用 / Log container DOM ref
const logBodyRef = ref<HTMLElement | null>(null)

// 新日志到达时自动滚动到底部 / Auto-scroll to bottom when new logs arrive
watch(() => displayLogs.value.length, async () => {
  if (!autoScroll.value || !logBodyRef.value) return
  await nextTick()
  logBodyRef.value.scrollTop = logBodyRef.value.scrollHeight
})
</script>

<template>
  <div v-if="hasLogs" class="log-panel" :style="{ height: panelHeight }">
    <!-- 拖拽手柄 / Drag handle -->
    <div v-if="!collapsed" class="drag-handle" @mousedown="onDragHandleMousedown" />

    <!-- Toggle bar / 切换栏 -->
    <div class="panel-toggle" @click="toggleCollapse">
      <span class="toggle-icon">{{ collapsed ? '▲' : '▼' }}</span>
      <span class="toggle-title">{{ t('editor.logPanel.title') }}</span>

      <template v-if="!collapsed">
        <!-- Tabs / 标签页 -->
        <a-radio-group
          v-model:value="activeTab"
          size="small"
          button-style="solid"
          style="margin-left: 12px"
          @click.stop
        >
          <a-radio-button value="executor" :disabled="!latestExecutorSession">
            ▶ {{ t('home.executorTitle') }}
            <span v-if="executorStatus === 'running'" class="status-dot running">●</span>
            <span v-else-if="executorStatus === 'completed'" class="status-dot completed">✓</span>
          </a-radio-button>
          <a-radio-button value="converter" :disabled="!latestConverterSession">
            ⟳ {{ t('home.converterTitle') }}
            <span v-if="converterStatus === 'running'" class="status-dot running">●</span>
            <span v-else-if="converterStatus === 'completed'" class="status-dot completed">✓</span>
          </a-radio-button>
        </a-radio-group>

        <span style="flex: 1" />

        <a-button size="small" type="text" @click.stop="autoScroll = !autoScroll">
          {{ autoScroll ? '🔽' : '🔼' }}
        </a-button>
      </template>
    </div>

    <!-- Log body / 日志主体 -->
    <div v-if="!collapsed" class="panel-body" ref="logBodyRef">
      <div
        v-for="(line, i) in displayLogs"
        :key="i"
        class="log-line"
        :class="'log-' + line.level"
      >
        <span class="log-ts">{{ line.ts }}</span>
        <span class="log-msg">{{ line.message }}</span>
      </div>
      <div v-if="displayLogs.length === 0" class="log-empty">
        {{ t('editor.logPanel.noOutput') }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.log-panel {
  border-top: 1px solid #e8e8e8;
  background: #1e1e1e;
  transition: height 0.2s;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}
/* 拖拽手柄（面板顶部）/ Drag handle (top of panel) */
.drag-handle {
  height: 6px;
  cursor: row-resize;
  flex-shrink: 0;
  background: transparent;
  position: relative;
  z-index: 10;
}
/* 扩展可点击区域 / Expand clickable area */
.drag-handle::before {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  top: -4px;
  bottom: -4px;
}
.drag-handle:hover {
  background: #fa8c16;
}
.panel-toggle {
  display: flex;
  align-items: center;
  padding: 6px 12px;
  cursor: pointer;
  background: #2d2d2d;
  user-select: none;
  flex-shrink: 0;
  height: 32px;
}
.panel-toggle:hover {
  background: #333;
}
.toggle-icon {
  font-size: 10px;
  color: #999;
  margin-right: 8px;
}
.toggle-title {
  font-size: 12px;
  color: #ccc;
  font-weight: 500;
}
.status-dot {
  font-size: 10px;
  margin-left: 4px;
}
.status-dot.running { color: #1890ff; }
.status-dot.completed { color: #52c41a; }

.panel-body {
  flex: 1;
  overflow-y: auto;
  padding: 4px 0;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.5;
}
.log-line {
  padding: 1px 16px;
  display: flex;
  gap: 10px;
}
.log-line:hover {
  background: rgba(255,255,255,0.03);
}
.log-ts {
  color: #666;
  flex-shrink: 0;
  font-size: 11px;
}
.log-info .log-msg { color: #e0e0e0; }
.log-warn .log-msg { color: #ffd54f; }
.log-error .log-msg { color: #ef5350; }
.log-empty {
  padding: 16px;
  text-align: center;
  color: #666;
}
</style>
