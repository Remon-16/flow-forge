<script setup lang="ts">
// ExecutorView — 用例执行器页面。
// Case executor view: toolbar + sidebar + content area + terminate bar.
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Modal } from 'ant-design-vue'
import { useExecutorStore } from '../stores/executor'
import { useAgentStore } from '../stores/agent'
import { isDesktop, openInExplorer } from '../utils/desktop-bridge'
import { SettingOutlined } from '@ant-design/icons-vue'
import AgentSettings from '../components/agent/AgentSettings.vue'
import ExecutorSidebar from '../components/executor/ExecutorSidebar.vue'
import ExecutorForm from '../components/executor/ExecutorForm.vue'

const router = useRouter()
const { t } = useI18n()
const executor = useExecutorStore()
const agent = useAgentStore()

const settingsVisible = ref(false)
const isDesktopMode = isDesktop

onMounted(async () => {
  await executor.initialize()
})

// 在默认浏览器中打开报告 / Open report in default browser
function openReport(path: string) {
  // 尝试使用 Tauri shell 打开 / Try opening with Tauri shell
  window.open(`file:///${path.replace(/\\/g, '/')}`, '_blank')
}

// 在文件资源管理器中打开 / Open in file explorer
function browsePath(path: string) {
  openInExplorer(path).catch(() => {
    // fallback: do nothing
  })
}
</script>

<template>
  <div class="executor-view">
    <!-- Toolbar -->
    <div class="toolbar">
      <a-button size="small" @click="router.push('/')">
        ← {{ t('executor.backHome') }}
      </a-button>
      <span class="toolbar-title">{{ t('executor.title') }}</span>
      <a-button size="small" @click="settingsVisible = true" :title="t('agent.settings')">
        <SettingOutlined />
      </a-button>
    </div>

    <!-- Desktop-only check -->
    <div v-if="!isDesktopMode" class="desktop-warning">
      <a-alert type="warning" :message="t('executor.desktopOnly')" show-icon />
    </div>

    <!-- Main layout -->
    <div class="main">
      <ExecutorSidebar
        @select-session="executor.selectSession"
        @delete-session="(id) => {
          Modal.confirm({
            title: t('executor.deleteSession'),
            content: t('executor.deleteSessionConfirm'),
            okText: t('dialog.yes'),
            cancelText: t('dialog.cancel'),
            onOk: () => executor.removeSession(id),
          })
        }"
        @new-session="executor.selectSession(null)"
      />

      <!-- Content area -->
      <div class="content">
        <!-- No session selected / 未选择会话 -->
        <div v-if="!executor.activeSession" class="content-empty">
          <ExecutorForm />
        </div>

        <template v-else>
          <!-- Pending -->
          <div v-if="executor.activeSession.status === 'pending'" class="content-pending">
            <ExecutorForm />
          </div>

          <!-- Running: log view -->
          <div v-else-if="executor.activeSession.status === 'running'" class="content-running">
            <div class="log-view">
              <div class="log-header">
                <span>{{ t('executor.running') }}</span>
              </div>
              <div class="log-body">
                <div
                  v-for="(line, i) in executor.activeSession.logLines"
                  :key="i"
                  class="log-line"
                  :class="'log-' + line.level"
                >
                  <span class="log-ts">{{ line.ts }}</span>
                  <span class="log-msg">{{ line.message }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- Completed -->
          <div v-else-if="executor.activeSession.status === 'completed'" class="content-completed">
            <div class="completed-card">
              <div class="completed-icon">✓</div>
              <h3>{{ t('executor.completed') }}</h3>
              <div v-if="executor.activeSession.summary" class="stats">
                <a-tag color="blue">
                  {{ t('executor.singleCases') }}: {{ executor.activeSession.summary.single_cases }}
                </a-tag>
                <a-tag color="green">
                  {{ t('executor.bizFlows') }}: {{ executor.activeSession.summary.biz_flows }}
                </a-tag>
              </div>
              <div v-if="executor.activeSession.reportPath" class="report-link">
                <a-button type="primary" @click="openReport(executor.activeSession.reportPath!)">
                  📄 {{ t('executor.reportOpen') }}
                </a-button>
                <a-button @click="browsePath(executor.activeSession.reportPath!)" style="margin-left: 8px">
                  📂 {{ t('executor.reportShowInFolder') }}
                </a-button>
              </div>
            </div>

            <!-- 日志折叠 / Collapsible log -->
            <a-collapse style="margin: 16px">
              <a-collapse-panel :header="t('executor.logTitle')" key="log">
                <div class="log-body compact">
                  <div
                    v-for="(line, i) in executor.activeSession.logLines"
                    :key="i"
                    class="log-line"
                    :class="'log-' + line.level"
                  >
                    <span class="log-ts">{{ line.ts }}</span>
                    <span class="log-msg">{{ line.message }}</span>
                  </div>
                </div>
              </a-collapse-panel>
            </a-collapse>
          </div>

          <!-- Error -->
          <div v-else-if="executor.activeSession.status === 'error'" class="content-error">
            <a-alert
              type="error"
              :message="executor.activeSession.error || t('executor.unknownError')"
              show-icon
              style="margin: 16px"
            />
            <div class="log-body" style="margin: 16px">
              <div
                v-for="(line, i) in executor.activeSession.logLines"
                :key="i"
                class="log-line"
                :class="'log-' + line.level"
              >
                <span class="log-ts">{{ line.ts }}</span>
                <span class="log-msg">{{ line.message }}</span>
              </div>
            </div>
          </div>
        </template>
      </div>
    </div>

    <!-- Terminate bar -->
    <div
      v-if="executor.activeSession && executor.activeSession.status === 'running'"
      class="terminate-bar"
    >
      <a-button
        danger
        size="small"
        @click="Modal.confirm({
          title: t('executor.terminate'),
          content: t('executor.terminateConfirm'),
          okText: t('dialog.yes'),
          cancelText: t('dialog.cancel'),
          okType: 'danger',
          onOk: () => executor.terminateSession(executor.activeSession!.id),
        })"
      >
        ⏹ {{ t('executor.terminate') }}
      </a-button>
    </div>

    <!-- Settings modal -->
    <AgentSettings v-model:visible="settingsVisible" />
  </div>
</template>

<style scoped>
.executor-view {
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #f5f5f5;
}
.toolbar {
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
.main {
  flex: 1;
  display: flex;
  overflow: hidden;
}
.content {
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
.content-completed, .content-error {
  flex: 1;
  overflow-y: auto;
}

/* Log view / 日志视图 */
.log-view {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.log-header {
  padding: 8px 16px;
  background: #2d2d2d;
  color: #ccc;
  font-size: 12px;
  font-weight: 500;
}
.log-body {
  flex: 1;
  overflow-y: auto;
  background: #1e1e1e;
  padding: 8px 0;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.6;
}
.log-body.compact {
  max-height: 300px;
}
.log-line {
  padding: 1px 16px;
  display: flex;
  gap: 12px;
}
.log-line:hover {
  background: rgba(255,255,255,0.05);
}
.log-ts {
  color: #666;
  flex-shrink: 0;
  font-size: 12px;
}
.log-info .log-msg { color: #d4d4d4; }
.log-warn .log-msg { color: #e6db74; }
.log-error .log-msg { color: #f92672; }

/* Completed / 完成 */
.completed-card {
  text-align: center;
  padding: 32px;
}
.completed-icon {
  font-size: 48px;
  color: #52c41a;
}
.completed-card h3 {
  margin: 12px 0;
  font-size: 20px;
}
.stats {
  margin: 12px 0;
  display: flex;
  gap: 8px;
  justify-content: center;
}
.report-link {
  margin: 16px 0;
}

/* Terminate / 终止 */
.terminate-bar {
  padding: 6px 16px;
  border-top: 1px solid #e8e8e8;
  background: #fff;
  display: flex;
  justify-content: flex-end;
}
</style>
