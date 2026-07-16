<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Modal, message } from 'ant-design-vue'
import { useAgentStore } from '../stores/agent'
import { isDesktop } from '../utils/desktop-bridge'
import { SettingOutlined } from '@ant-design/icons-vue'
import AgentSettings from '../components/agent/AgentSettings.vue'
import TaskSidebar from '../components/agent/TaskSidebar.vue'
import NewTaskForm from '../components/agent/NewTaskForm.vue'
import RunningView from '../components/agent/RunningView.vue'
import QuestionPrompt from '../components/agent/QuestionPrompt.vue'
import CompletedView from '../components/agent/CompletedView.vue'

const router = useRouter()
const { t } = useI18n()
const agent = useAgentStore()

const settingsVisible = ref(false)
const isDesktopMode = isDesktop

onMounted(async () => {
  await agent.initialize()
})
</script>

<template>
  <div class="agent-view">
    <!-- Toolbar -->
    <div class="agent-toolbar">
      <a-button size="small" @click="router.push('/')">
        ← {{ t('agent.backHome') }}
      </a-button>
      <span class="toolbar-title">{{ t('agent.title') }}</span>
      <a-button size="small" @click="settingsVisible = true" :title="t('agent.settings')">
        <SettingOutlined />
      </a-button>
    </div>

    <!-- Desktop-only check -->
    <div v-if="!isDesktopMode" class="desktop-warning">
      <a-alert
        type="warning"
        :message="t('agent.desktopOnly')"
        show-icon
      />
    </div>

    <!-- Main layout -->
    <div class="agent-main">
      <TaskSidebar
        @select-task="agent.selectTask"
        @delete-task="(id) => {
          Modal.confirm({
            title: t('agent.deleteTask'),
            content: t('agent.deleteTaskContent'),
            okText: t('dialog.yes'),
            cancelText: t('dialog.cancel'),
            onOk: () => agent.removeTask(id),
          })
        }"
        @new-task="agent.selectTask(null)"
      />

      <!-- Content area -->
      <div class="agent-content">
        <!-- No task selected / 未选择任务 -->
        <div v-if="!agent.activeTask" class="content-empty">
          <NewTaskForm @submit="() => {}" />
        </div>

        <!-- Task selected / 已选择任务 -->
        <template v-else>
          <!-- Pending: new task form -->
          <div v-if="agent.activeTask.status === 'pending'" class="content-pending">
            <NewTaskForm @submit="() => {}" />
          </div>

          <!-- Running: log view + optional prompt -->
          <div v-else-if="agent.activeTask.status === 'running'" class="content-running">
            <RunningView />
          </div>

          <!-- Question: log view + prompt interaction -->
          <div v-else-if="agent.activeTask.status === 'question'" class="content-question">
            <RunningView />
            <QuestionPrompt />
          </div>

          <!-- Completed: summary -->
          <div v-else-if="agent.activeTask.status === 'completed'" class="content-completed">
            <CompletedView />
          </div>

          <!-- Error: error message -->
          <div v-else-if="agent.activeTask.status === 'error'" class="content-error">
            <RunningView />
            <div class="error-overlay">
              <a-alert
                type="error"
                :message="agent.activeTask.error || t('agent.unknownError')"
                show-icon
              />
              <a-button
                type="primary"
                style="margin-top: 12px;"
                @click="agent.startResumeTask(agent.activeTask!.id, [])"
              >
                {{ t('agent.retry') }}
              </a-button>
            </div>
          </div>
        </template>
      </div>
    </div>

    <!-- Task terminate button (when running) -->
    <div
      v-if="agent.activeTask && (agent.activeTask.status === 'running' || agent.activeTask.status === 'question')"
      class="terminate-bar"
    >
      <a-button
        danger
        size="small"
        @click="Modal.confirm({
          title: t('agent.terminate'),
          content: t('agent.terminateConfirm'),
          okText: t('dialog.yes'),
          cancelText: t('dialog.cancel'),
          okType: 'danger',
          onOk: () => agent.terminateTask(agent.activeTask!.id),
        })"
      >
        ⏹ {{ t('agent.terminate') }}
      </a-button>
    </div>

    <!-- Settings modal -->
    <AgentSettings v-model:visible="settingsVisible" />
  </div>
</template>

<style scoped>
.agent-view {
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #f5f5f5;
}
.agent-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  border-bottom: 1px solid #e8e8e8;
  background: #fff;
  flex-shrink: 0;
  height: 40px;
}
.toolbar-title {
  flex: 1;
  font-size: 14px;
  font-weight: 600;
  color: #333;
}
.desktop-warning {
  padding: 8px 16px;
}
.agent-main {
  flex: 1;
  display: flex;
  overflow: hidden;
}
.agent-content {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.content-empty, .content-pending {
  flex: 1;
  overflow: hidden;
}
.content-running, .content-question {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.content-completed, .content-error {
  flex: 1;
  overflow-y: auto;
}
.error-overlay {
  padding: 16px;
  border-top: 2px solid #ff4d4f;
  background: #fff2f0;
}
.terminate-bar {
  padding: 6px 16px;
  border-top: 1px solid #e8e8e8;
  background: #fff;
  display: flex;
  justify-content: flex-end;
}
</style>
