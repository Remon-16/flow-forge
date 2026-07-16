<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAgentStore } from '../../stores/agent'
import type { TaskStatus } from '../../types/agent'

const { t } = useI18n()
const agent = useAgentStore()

const emit = defineEmits<{
  selectTask: [taskId: string]
  deleteTask: [taskId: string]
  newTask: []
}>()

const statusIcon = (s: TaskStatus): string => {
  switch (s) {
    case 'pending': return '○'
    case 'running': return '◉'
    case 'question': return '⬤'
    case 'completed': return '✓'
    case 'error': return '✗'
    default: return '○'
  }
}

const statusClass = (s: TaskStatus): string => `status-${s}`

const hasNotify = (taskId: string): boolean =>
  agent.unreadPrompts.has(taskId)
</script>

<template>
  <div class="task-sidebar">
    <div class="sidebar-header">
      <span class="header-title">Sessions</span>
      <a-button size="small" type="dashed" @click="emit('newTask')">
        + {{ t('agent.newTask') }}
      </a-button>
    </div>

    <div class="task-list">
      <div
        v-for="task in agent.sortedTasks"
        :key="task.id"
        class="task-item"
        :class="{ active: agent.activeTaskId === task.id, [statusClass(task.status)]: true }"
        @click="emit('selectTask', task.id)"
      >
        <span class="task-status-icon" :class="statusClass(task.status)">
          {{ statusIcon(task.status) }}
        </span>
        <span class="task-name">{{ task.name }}</span>
        <span v-if="hasNotify(task.id)" class="notify-dot" />
        <a-button
          size="small"
          type="text"
          danger
          class="task-delete-btn"
          @click.stop="emit('deleteTask', task.id)"
        >
          🗑
        </a-button>
      </div>

      <div v-if="agent.tasks.length === 0" class="no-tasks">
        {{ t('agent.noTask') }}
      </div>
    </div>

  </div>
</template>

<style scoped>
.task-sidebar {
  width: 260px;
  min-width: 260px;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #fafafa;
  border-right: 1px solid #e8e8e8;
}
.sidebar-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 16px;
  border-bottom: 1px solid #eee;
}
.header-title {
  font-weight: 600;
  font-size: 13px;
}
.task-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}
.task-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  cursor: pointer;
  border-radius: 6px;
  margin-bottom: 2px;
  position: relative;
}
.task-item:hover { background: #e8e8e8; }
.task-item.active { background: #d6e4ff; }
.task-status-icon {
  font-size: 14px;
  min-width: 18px;
  text-align: center;
}
.task-name {
  flex: 1;
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.notify-dot {
  width: 8px;
  height: 8px;
  background: #ff4d4f;
  border-radius: 50%;
}
.task-delete-btn {
  opacity: 0;
  font-size: 12px;
  padding: 0 4px;
  min-width: auto;
  height: 22px;
}
.task-item:hover .task-delete-btn { opacity: 1; }
.status-pending .task-status-icon { color: #999; }
.status-running .task-status-icon { color: #1677ff; }
.status-question .task-status-icon { color: #fa8c16; }
.status-completed .task-status-icon { color: #52c41a; }
.status-error .task-status-icon { color: #ff4d4f; }
.no-tasks {
  padding: 32px 16px;
  text-align: center;
  color: #999;
  font-size: 13px;
}
</style>
