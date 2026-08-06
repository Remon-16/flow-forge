<script setup lang="ts">
// CounterSidebar — 诊断计数器会话列表侧边栏。
// Diagnostic counter session sidebar: lists all sessions sorted by updatedAt.
// 完全对应 ExecutorSidebar.vue / Mirrors ExecutorSidebar.vue exactly.
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useCounterStore } from '../../stores/counter'
import type { CounterStatus } from '../../types/counter'

const { t } = useI18n()
const store = useCounterStore()

const emit = defineEmits<{
  'select-session': [id: string]
  'delete-session': [id: string]
  'new-session': []
}>()

const sorted = computed(() => store.sortedSessions)

function statusIcon(status: CounterStatus): string {
  switch (status) {
    case 'pending': return '○'
    case 'running': return '◉'
    case 'completed': return '✓'
    case 'error': return '✗'
  }
}

function statusClass(status: CounterStatus): string {
  return `status-${status}`
}

function formatDate(ts: number): string {
  return new Date(ts).toLocaleString()
}
</script>

<template>
  <div class="sidebar">
    <div class="sidebar-header">
      <span class="sidebar-title">{{ t('counter.sidebarTitle') }}</span>
      <a-button size="small" type="dashed" @click="emit('new-session')">
        + {{ t('counter.newSession') }}
      </a-button>
    </div>

    <div class="session-list">
      <div
        v-for="s in sorted"
        :key="s.id"
        class="session-item"
        :class="{ active: s.id === store.activeSessionId }"
        @click="emit('select-session', s.id)"
      >
        <span class="session-status" :class="statusClass(s.status)">
          {{ statusIcon(s.status) }}
        </span>
        <div class="session-info">
          <span class="session-name">{{ s.name }}</span>
          <span class="session-time">{{ formatDate(s.updatedAt) }}</span>
        </div>
        <a-button
          type="text"
          size="small"
          class="delete-btn"
          @click.stop="emit('delete-session', s.id)"
        >
          ×
        </a-button>
      </div>

      <div v-if="sorted.length === 0" class="empty-hint">
        {{ t('counter.noSessions') }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.sidebar {
  width: 260px;
  height: 100%;
  display: flex;
  flex-direction: column;
  border-right: 1px solid #e8e8e8;
  background: #fafafa;
  flex-shrink: 0;
}
.sidebar-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 16px;
  border-bottom: 1px solid #e8e8e8;
}
.sidebar-title {
  font-size: 13px;
  font-weight: 600;
  color: #666;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.session-list {
  flex: 1;
  overflow-y: auto;
}
.session-item {
  display: flex;
  align-items: center;
  padding: 10px 16px;
  cursor: pointer;
  border-bottom: 1px solid #f0f0f0;
  gap: 10px;
  transition: background 0.15s;
}
.session-item:hover {
  background: #f0f0f0;
}
.session-item.active {
  background: #e6f7ff;
  border-left: 3px solid #1890ff;
}
.session-status {
  font-size: 14px;
  flex-shrink: 0;
  width: 20px;
  text-align: center;
}
.status-pending { color: #999; }
.status-running { color: #1890ff; }
.status-completed { color: #52c41a; }
.status-error { color: #ff4d4f; }
.session-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.session-name {
  font-size: 13px;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.session-time {
  font-size: 11px;
  color: #999;
}
.delete-btn {
  opacity: 0;
  transition: opacity 0.15s;
  color: #999;
}
.session-item:hover .delete-btn {
  opacity: 1;
}
.empty-hint {
  padding: 24px 16px;
  text-align: center;
  color: #bbb;
  font-size: 13px;
}
</style>
