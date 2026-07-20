<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Modal } from 'ant-design-vue'
import { useAgentStore } from '../stores/agent'
import { isDesktop } from '../utils/desktop-bridge'
import { SettingOutlined } from '@ant-design/icons-vue'
import AgentSettings from '../components/agent/AgentSettings.vue'
import TaskSidebar from '../components/agent/TaskSidebar.vue'
import NewTaskForm from '../components/agent/NewTaskForm.vue'
import RunningView from '../components/agent/RunningView.vue'
import QuestionPrompt from '../components/agent/QuestionPrompt.vue'
import CompletedView from '../components/agent/CompletedView.vue'
import AnnotatorPanel from '../components/annotator/AnnotatorPanel.vue'
import ResizableDivider from '../components/layout/ResizableDivider.vue'
import { useSplitter } from '../composables/useSplitter'
import type { PlanReviewData } from '../types/agent'

const router = useRouter()
const { t } = useI18n()
const agent = useAgentStore()

const settingsVisible = ref(false)
const isDesktopMode = isDesktop

// 是否为计划审核状态 — 决定是否显示右侧批注器
// Whether in plan review mode — controls right annotator visibility
const isPlanReview = computed(() =>
  agent.activeTask?.pendingPrompt?.kind === 'plan_review'
)

// 是否为 API 澄清状态 — 决定是否显示下方面板（无右侧批注器）
// Whether in API clarification mode — controls bottom panel (no right annotator)
const isApiClarification = computed(() =>
  agent.activeTask?.pendingPrompt?.kind === 'api_clarification'
)

// Plan review 的 memory_dir / memory_dir from plan_review prompt
const reviewMemoryDir = computed(() => {
  if (!isPlanReview.value) return ''
  const promptData = agent.activeTask?.pendingPrompt as PlanReviewData | undefined
  return promptData?.data?.memory_dir || ''
})

// 批注器显示/隐藏 / Annotator visibility toggle
// 右侧批注器默认关闭，用户通过 QuestionPrompt 按钮手动打开 / Right annotator default closed, user opens via QuestionPrompt button
const annotatorVisible = ref(false)

// ===================================================================
// 可拖拽分隔条 / Resizable splitters
// ===================================================================

// 下方审核面板高度 (horizontal splitter)
const bottomSplitter = useSplitter({
  direction: 'horizontal',
  defaultSize: 220,
  minSize: 100,
  maxSize: 600,
  reverse: true,
})

// 右侧批注器宽度 (vertical splitter)
const rightSplitter = useSplitter({
  direction: 'vertical',
  defaultSize: 500,
  minSize: 300,
  maxSize: 900,
  reverse: true,
})

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
            onOk: () => { agent.removeTask(id).catch(() => {}) },
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

          <!-- Running: log view -->
          <div v-else-if="agent.activeTask.status === 'running'" class="content-running">
            <RunningView />
          </div>

          <!-- Question: 审核时三栏布局（日志 + 底栏 + 右侧批注器） -->
          <!-- Question: three-column layout for review (logs + bottom panel + right annotator) -->
          <div
            v-else-if="agent.activeTask.status === 'question'"
            class="content-question"
            :class="{
              'layout-review': isPlanReview,
              'layout-clarify': isApiClarification,
            }"
          >
            <!-- 中间区域：日志 + 下方面板 / Center: logs + bottom panel -->
            <div class="content-center" :class="{ 'has-bottom': isPlanReview || isApiClarification }">
              <RunningView />
              <template v-if="isPlanReview || isApiClarification">
                <ResizableDivider
                  orientation="horizontal"
                  @mousedown="bottomSplitter.onDividerMousedown"
                />
                <div
                  class="bottom-panel"
                  :style="{ height: bottomSplitter.size.value + 'px' }"
                >
                  <QuestionPrompt :annotator-visible="annotatorVisible"
                    @toggle-annotator="annotatorVisible = !annotatorVisible" />
                </div>
              </template>
            </div>

            <!-- 右侧批注器 (仅 plan_review) / Right annotator (plan_review only) -->
            <template v-if="isPlanReview && annotatorVisible">
              <ResizableDivider
                orientation="vertical"
                @mousedown="rightSplitter.onDividerMousedown"
              />
              <div
                class="annotator-right"
                :style="{ width: rightSplitter.size.value + 'px' }"
              >
                <AnnotatorPanel
                  :memory-dir="reviewMemoryDir"
                  :show-toolbar="true"
                  :default-sidebar-visible="false"
                />
              </div>
            </template>
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
          onOk: () => { agent.terminateTask(agent.activeTask!.id).catch(() => {}) },
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
.content-running {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* Question 状态 / Question state */
.content-question {
  flex: 1;
  display: flex;
  overflow: hidden;
}
/* 计划审核 — 三栏 / Plan review — three columns */
.content-question.layout-review {
  flex-direction: row;
}
/* API 澄清 — 单栏 / API clarification — single column */
.content-question.layout-clarify {
  flex-direction: column;
}

/* 中间区域 / Center area */
.content-center {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
}
.content-center.has-bottom {
  /* RunningView 在上，QuestionPrompt 在下 */
}

/* 下方审核面板 / Bottom review panel */
.bottom-panel {
  flex-shrink: 0;
  overflow-y: auto;
  border-top: 2px solid #fa8c16;
  background: #fff7e6;
}

/* 右侧批注器 / Right annotator */
.annotator-right {
  flex-shrink: 0;
  overflow: hidden;
  border-left: 2px solid #fa8c16;
  background: #fff;
}

/* Completed / Error states */
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
