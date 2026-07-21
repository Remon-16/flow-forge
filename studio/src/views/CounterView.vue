<script setup lang="ts">
// CounterView — 诊断计数器页面。
// Diagnostic counter view: toolbar + sidebar + content area + terminate bar.
// 完全对应 ExecutorView.vue / Mirrors ExecutorView.vue exactly.
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Modal } from 'ant-design-vue'
import { useCounterStore } from '../stores/counter'
import { isDesktop, openInExplorer } from '../utils/desktop-bridge'
import { SettingOutlined } from '@ant-design/icons-vue'
import AgentSettings from '../components/agent/AgentSettings.vue'
import CounterSidebar from '../components/counter/CounterSidebar.vue'
import CounterForm from '../components/counter/CounterForm.vue'

const router = useRouter()
const { t } = useI18n()
const counter = useCounterStore()

const settingsVisible = ref(false)
const isDesktopMode = isDesktop

onMounted(async () => {
  await counter.initialize()
})

// 在文件资源管理器中打开输出目录 / Open output directory in file explorer
function browsePath(path: string) {
  openInExplorer(path).catch(() => {
    // fallback: do nothing
  })
}
</script>

<template>
  <div class="counter-view">
    <!-- Toolbar -->
    <div class="toolbar">
      <a-button size="small" @click="router.push('/')">
        ← {{ t('counter.backHome') }}
      </a-button>
      <span class="toolbar-title">{{ t('counter.title') }}</span>
      <a-button size="small" @click="settingsVisible = true" :title="t('agent.settings')">
        <SettingOutlined />
      </a-button>
    </div>

    <!-- Desktop-only check -->
    <div v-if="!isDesktopMode" class="desktop-warning">
      <a-alert type="warning" :message="t('counter.desktopOnly')" show-icon />
    </div>

    <!-- Main layout -->
    <div class="main">
      <CounterSidebar
        @select-session="counter.selectSession"
        @delete-session="(id) => {
          Modal.confirm({
            title: t('counter.deleteSession'),
            content: t('counter.deleteSessionConfirm'),
            okText: t('dialog.yes'),
            cancelText: t('dialog.cancel'),
            onOk: () => { counter.removeSession(id).catch(() => {}) },
          })
        }"
        @new-session="counter.selectSession(null)"
      />

      <!-- Content area -->
      <div class="content">
        <!-- No session selected / 未选择会话 -->
        <div v-if="!counter.activeSession" class="content-empty">
          <CounterForm />
        </div>

        <template v-else>
          <!-- Pending -->
          <div v-if="counter.activeSession.status === 'pending'" class="content-pending">
            <CounterForm />
          </div>

          <!-- Running: log view -->
          <div v-else-if="counter.activeSession.status === 'running'" class="content-running">
            <div class="log-view">
              <div class="log-header">
                <span>{{ t('counter.running') }}</span>
              </div>
              <div class="log-body">
                <div
                  v-for="(line, i) in counter.activeSession.logLines"
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
          <div v-else-if="counter.activeSession.status === 'completed'" class="content-completed">
            <div class="completed-card">
              <div class="completed-icon">✓</div>
              <h3>{{ t('counter.completed') }}</h3>
              <div v-if="counter.activeSession.totalCounts !== undefined" class="stats">
                <a-tag color="blue">
                  {{ t('counter.totalCounts', { count: counter.activeSession.totalCounts }) }}
                </a-tag>
              </div>
              <div class="report-link">
                <a-button @click="browsePath(counter.activeSession.outputDir)" style="margin-left: 8px">
                  📂 {{ t('executor.reportShowInFolder') }}
                </a-button>
              </div>
            </div>

            <!-- 日志折叠 / Collapsible log -->
            <a-collapse style="margin: 16px">
              <a-collapse-panel :header="t('counter.logTitle')" key="log">
                <div class="log-body compact">
                  <div
                    v-for="(line, i) in counter.activeSession.logLines"
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
          <div v-else-if="counter.activeSession.status === 'error'" class="content-error">
            <a-alert
              type="error"
              :message="counter.activeSession.error || t('counter.unknownError')"
              show-icon
              style="margin: 16px"
            />
            <div class="log-body" style="margin: 16px">
              <div
                v-for="(line, i) in counter.activeSession.logLines"
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
      v-if="counter.activeSession && counter.activeSession.status === 'running'"
      class="terminate-bar"
    >
      <a-button
        danger
        size="small"
        @click="Modal.confirm({
          title: t('counter.terminate'),
          content: t('counter.terminateConfirm'),
          okText: t('dialog.yes'),
          cancelText: t('dialog.cancel'),
          okType: 'danger',
          onOk: () => { counter.terminateSession(counter.activeSession!.id).catch(() => {}) },
        })"
      >
        ⏹ {{ t('counter.terminate') }}
      </a-button>
    </div>

    <!-- Settings modal -->
    <AgentSettings v-model:visible="settingsVisible" />
  </div>
</template>

<style scoped>
.counter-view {
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
.log-info .log-msg { color: #e0e0e0; }
.log-warn .log-msg { color: #ffd54f; }
.log-error .log-msg { color: #ef5350; }

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
