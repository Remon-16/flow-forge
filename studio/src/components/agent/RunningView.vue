<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAgentStore } from '../../stores/agent'
import type { LogEntry } from '../../types/agent'

const { t } = useI18n()
const agent = useAgentStore()

const logContainer = ref<HTMLElement | null>(null)
const autoScroll = ref(true)

const logs = ref<LogEntry[]>([])

// 同步日志 / Sync logs from store
watch(
  () => agent.activeTask?.logLines,
  (lines) => {
    if (lines) logs.value = [...lines]
  },
  { immediate: true, deep: true },
)

// 自动滚动 / Auto-scroll
watch(
  () => logs.value.length,
  () => {
    if (autoScroll.value) {
      nextTick(() => {
        if (logContainer.value) {
          logContainer.value.scrollTop = logContainer.value.scrollHeight
        }
      })
    }
  },
)

function onScroll() {
  if (!logContainer.value) return
  const el = logContainer.value
  autoScroll.value = el.scrollTop + el.clientHeight >= el.scrollHeight - 20
}
</script>

<template>
  <div class="running-view">
    <div class="log-header">
      <span style="font-weight: 600; font-size: 13px;">Logs</span>
      <a-tag color="processing" size="small">{{ t('agent.status_running') }}</a-tag>
      <div style="flex: 1;" />
      <a-button size="small" type="text" @click="autoScroll = !autoScroll">
        {{ autoScroll ? '↓' : '⊘' }} {{ t('agent.log_autoScroll') }}
      </a-button>
    </div>

    <div class="log-area" ref="logContainer" @scroll="onScroll">
      <div v-if="logs.length === 0" class="log-empty">
        Waiting for agent output...
      </div>
      <div
        v-for="(log, i) in logs"
        :key="i"
        class="log-line"
        :class="`log-${log.level}`"
      >
        <span class="log-ts">{{ log.ts }}</span>
        <span class="log-msg">{{ log.message }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.running-view {
  height: 100%;
  display: flex;
  flex-direction: column;
}
.log-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  border-bottom: 1px solid #e8e8e8;
  background: #fff;
}
.log-area {
  flex: 1;
  overflow-y: auto;
  background: #1e1e1e;
  color: #d4d4d4;
  font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
  font-size: 12px;
  padding: 12px 16px;
  line-height: 1.6;
}
.log-empty {
  color: #666;
  font-style: italic;
}
.log-line {
  display: flex;
  gap: 12px;
  white-space: pre-wrap;
  word-break: break-all;
}
.log-ts {
  color: #666;
  flex-shrink: 0;
}
.log-info .log-msg { color: #e0e0e0; }
.log-warn .log-msg { color: #ffd54f; }
.log-error .log-msg { color: #ef5350; }
</style>
