<script setup lang="ts">
// ConverterView — 用例转换器页面。
// Case converter view: toolbar + sidebar + content area + terminate bar.
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Modal } from 'ant-design-vue'
import { useConverterStore } from '../stores/converter'
import { isDesktop, openInExplorer } from '../utils/desktop-bridge'
import { SettingOutlined } from '@ant-design/icons-vue'
import AgentSettings from '../components/agent/AgentSettings.vue'
import ConverterForm from '../components/converter/ConverterForm.vue'
import type { ConverterStatus } from '../types/converter'

const router = useRouter()
const { t } = useI18n()
const converter = useConverterStore()

const settingsVisible = ref(false)
const isDesktopMode = isDesktop

onMounted(async () => {
  await converter.initialize()
})

function statusIcon(status: ConverterStatus): string {
  switch (status) {
    case 'pending': return '○'
    case 'running': return '◉'
    case 'completed': return '✓'
    case 'error': return '✗'
  }
}

function statusClass(status: ConverterStatus): string {
  return `status-${status}`
}

function formatDate(ts: number): string {
  return new Date(ts).toLocaleString()
}
</script>

<template>
  <div class="converter-view">
    <!-- Toolbar -->
    <div class="toolbar">
      <a-button size="small" @click="router.push('/')">
        ← {{ t('converter.backHome') }}
      </a-button>
      <span class="toolbar-title">{{ t('converter.title') }}</span>
      <a-button size="small" @click="settingsVisible = true" :title="t('agent.settings')">
        <SettingOutlined />
      </a-button>
    </div>

    <!-- Desktop-only check -->
    <div v-if="!isDesktopMode" class="desktop-warning">
      <a-alert type="warning" :message="t('converter.desktopOnly')" show-icon />
    </div>

    <!-- Main layout -->
    <div class="main">
      <!-- Sidebar -->
      <div class="sidebar">
        <div class="sidebar-header">
          <span class="sidebar-title">{{ t('converter.sidebar_title') }}</span>
        </div>
        <div class="session-list">
          <div
            v-for="s in converter.sortedSessions"
            :key="s.id"
            class="session-item"
            :class="{ active: s.id === converter.activeSessionId }"
            @click="converter.selectSession(s.id)"
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
              @click.stop="Modal.confirm({
                title: t('converter.deleteSession'),
                content: t('converter.deleteSessionConfirm'),
                okText: t('dialog.yes'),
                cancelText: t('dialog.cancel'),
                onOk: () => converter.removeSession(s.id),
              })"
            >
              ×
            </a-button>
          </div>
          <div v-if="converter.sortedSessions.length === 0" class="empty-hint">
            {{ t('converter.noSessions') }}
          </div>
        </div>
        <div class="sidebar-footer">
          <a-button type="dashed" block @click="converter.selectSession(null)">
            + {{ t('converter.newSession') }}
          </a-button>
        </div>
      </div>

      <!-- Content area -->
      <div class="content">
        <div v-if="!converter.activeSession" class="content-empty">
          <ConverterForm />
        </div>

        <template v-else>
          <!-- Pending -->
          <div v-if="converter.activeSession.status === 'pending'" class="content-pending">
            <ConverterForm />
          </div>

          <!-- Running -->
          <div v-else-if="converter.activeSession.status === 'running'" class="content-running">
            <div class="log-view">
              <div class="log-header">
                <span>{{ t('converter.running') }}</span>
              </div>
              <div class="log-body">
                <div
                  v-for="(line, i) in converter.activeSession.logLines"
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
          <div v-else-if="converter.activeSession.status === 'completed'" class="content-completed">
            <div class="completed-card">
              <div class="completed-icon">✓</div>
              <h3>{{ t('converter.completed') }}</h3>
              <div v-if="converter.activeSession.outputLinkPath" class="output-link">
                <a-button
                  type="primary"
                  @click="openInExplorer(converter.activeSession!.outputLinkPath!).catch(() => {})"
                >
                  📂 {{ t('converter.outputOpen') }}
                </a-button>
              </div>
            </div>

            <a-collapse style="margin: 16px">
              <a-collapse-panel :header="t('executor.logTitle')" key="log">
                <div class="log-body compact">
                  <div
                    v-for="(line, i) in converter.activeSession.logLines"
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
          <div v-else-if="converter.activeSession.status === 'error'" class="content-error">
            <a-alert
              type="error"
              :message="converter.activeSession.error || t('converter.unknownError')"
              show-icon
              style="margin: 16px"
            />
            <div class="log-body" style="margin: 16px">
              <div
                v-for="(line, i) in converter.activeSession.logLines"
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
      v-if="converter.activeSession && converter.activeSession.status === 'running'"
      class="terminate-bar"
    >
      <a-button
        danger
        size="small"
        @click="Modal.confirm({
          title: t('converter.terminate'),
          content: t('converter.terminateConfirm'),
          okText: t('dialog.yes'),
          cancelText: t('dialog.cancel'),
          okType: 'danger',
          onOk: () => converter.terminateSession(converter.activeSession!.id),
        })"
      >
        ⏹ {{ t('converter.terminate') }}
      </a-button>
    </div>

    <!-- Settings modal -->
    <AgentSettings v-model:visible="settingsVisible" />
  </div>
</template>

<style scoped>
.converter-view {
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
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

/* Sidebar */
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
  padding: 12px 16px;
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
.sidebar-footer {
  padding: 12px;
  border-top: 1px solid #e8e8e8;
}

/* Content */
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

/* Log view */
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

/* Completed */
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
.output-link {
  margin: 16px 0;
}

/* Terminate */
.terminate-bar {
  padding: 6px 16px;
  border-top: 1px solid #e8e8e8;
  background: #fff;
  display: flex;
  justify-content: flex-end;
}
</style>
