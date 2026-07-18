<script setup lang="ts">
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useSettingsStore } from './stores/settings'
import { useWorkbookStore } from './stores/workbook'
import { useYamlStore } from './stores/yaml-store'
import { useAgentStore } from './stores/agent'
import { useExecutorStore } from './stores/executor'
import { useConverterStore } from './stores/converter'
import { isDesktop } from './utils/desktop-bridge'
import AppHeader from './components/layout/AppHeader.vue'
import AppSidebar from './components/layout/AppSidebar.vue'
import StatusBar from './components/layout/StatusBar.vue'
import { watch, computed, ref, onMounted, onUnmounted } from 'vue'

const route = useRoute()
const { t, locale } = useI18n()
const settings = useSettingsStore()
const workbook = useWorkbookStore()
const yamlStore = useYamlStore()
const agent = useAgentStore()
const executorStore = useExecutorStore()
const converterStore = useConverterStore()

const isHome = computed(() => route.name === 'home')
const isAnnotator = computed(() => route.name === 'plan-annotator')
const isAgent = computed(() => route.name === 'agent')
const isExecutor = computed(() => route.name === 'executor')
const isConverter = computed(() => route.name === 'converter')
const isYamlMode = computed(() => route.name === 'yaml-editor')

// 关闭确认弹窗状态 / Close confirmation dialog state
const closeDialogVisible = ref(false)
const closeDialogRunningCount = ref(0)

// 窗口关闭事件监听器清理函数 / Window close event listener cleanup
let _closeUnlisten: (() => void) | undefined

watch(
  () => settings.language,
  (lang) => {
    locale.value = lang
  },
  { immediate: true }
)

function onContentWheel(e: WheelEvent) {
  if (e.ctrlKey) {
    e.preventDefault()
    if (e.deltaY < 0) settings.zoomIn()
    else if (e.deltaY > 0) settings.zoomOut()
  }
}

function onBeforeUnload(e: BeforeUnloadEvent) {
  if (yamlStore.hasUnsavedTabs || workbook.modified) {
    e.preventDefault()
    e.returnValue = ''
  }
}

// 窗口关闭拦截 / Window close interception
async function handleMinimizeToTray() {
  closeDialogVisible.value = false
  const { getCurrentWindow } = await import('@tauri-apps/api/window')
  await getCurrentWindow().hide()
}

async function handleTerminateAndQuit() {
  closeDialogVisible.value = false
  // 终止 agent 任务 / Terminate agent tasks
  const runningTasks = agent.tasks.filter(
    t => t.status === 'running' || t.status === 'question'
  )
  for (const task of runningTasks) {
    await agent.terminateTask(task.id)
  }
  // 终止 executor 会话 / Terminate executor sessions
  const runningExec = executorStore.sessions.filter(s => s.status === 'running')
  for (const session of runningExec) {
    await executorStore.terminateSession(session.id)
  }
  // 终止 converter 会话 / Terminate converter sessions
  const runningConv = converterStore.sessions.filter(s => s.status === 'running')
  for (const session of runningConv) {
    await converterStore.terminateSession(session.id)
  }
  // 终止所有子进程后退出应用 / Kill all subprocesses then exit the app
  if (isDesktop) {
    const { invoke } = await import('@tauri-apps/api/core')
    await invoke('force_quit_app')
  } else {
    window.close()
  }
}

// 强制退出应用 / Force quit the application
async function handleForceQuit() {
  closeDialogVisible.value = false
  if (isDesktop) {
    const { invoke } = await import('@tauri-apps/api/core')
    await invoke('force_quit_app')
  } else {
    window.close()
  }
}

onMounted(async () => {
  window.addEventListener('beforeunload', onBeforeUnload)

  // 仅在桌面模式下拦截窗口关闭 / Only intercept in desktop mode
  if (!isDesktop) return

  // 监听来自 Rust 层的窗口关闭请求（绕过托盘图标对 CloseRequested 的拦截）
  // Listen for close request from Rust layer (bypasses tray interception of CloseRequested)
  try {
    const { listen } = await import('@tauri-apps/api/event')
    _closeUnlisten = await listen('window-close-requested', () => {
      const tasks = agent.tasks || []
      const agentRunning = tasks.filter(
        t => t.status === 'running' || t.status === 'question'
      )
      const execRunning = executorStore.sessions.filter(s => s.status === 'running')
      const convRunning = converterStore.sessions.filter(s => s.status === 'running')
      const totalRunning = agentRunning.length + execRunning.length + convRunning.length
      if (totalRunning > 0) {
        // 有运行中任务：弹框确认 / Running tasks: show confirmation dialog
        closeDialogRunningCount.value = totalRunning
        closeDialogVisible.value = true
      } else {
        // 无运行中任务：直接退出应用 / No running tasks: quit directly
        handleForceQuit()
      }
    })
  } catch (e) {
    console.warn('Failed to register close listener via Rust event, falling back to onCloseRequested', e)
    // 回退方案：如果 Rust 事件监听失败，尝试直接注册 onCloseRequested
    // Fallback: try direct onCloseRequested if Rust event listener fails
    const { getCurrentWindow } = await import('@tauri-apps/api/window')
    const appWindow = getCurrentWindow()
    _closeUnlisten = await appWindow.onCloseRequested((event) => {
      event.preventDefault()
      const tasks = agent.tasks || []
      const agentRunning = tasks.filter(
        t => t.status === 'running' || t.status === 'question'
      )
      const execRunning = executorStore.sessions.filter(s => s.status === 'running')
      const convRunning = converterStore.sessions.filter(s => s.status === 'running')
      const totalRunning = agentRunning.length + execRunning.length + convRunning.length
      if (totalRunning > 0) {
        closeDialogRunningCount.value = totalRunning
        closeDialogVisible.value = true
      } else {
        handleForceQuit()
      }
    })
  }
})

onUnmounted(() => {
  window.removeEventListener('beforeunload', onBeforeUnload)
  if (_closeUnlisten) _closeUnlisten()
})
</script>

<template>
  <!-- Home page: no chrome -->
  <div v-if="isHome" class="app-layout home-layout">
    <router-view />
  </div>

  <!-- Annotator page: no chrome, standalone -->
  <div v-else-if="isAnnotator" class="app-layout annotator-layout">
    <router-view />
  </div>

  <!-- Agent runner page: no chrome, standalone -->
  <div v-else-if="isAgent" class="app-layout agent-layout">
    <router-view />
  </div>

  <!-- Executor page: no chrome, standalone -->
  <div v-else-if="isExecutor" class="app-layout executor-layout">
    <router-view />
  </div>

  <!-- Converter page: no chrome, standalone -->
  <div v-else-if="isConverter" class="app-layout converter-layout">
    <router-view />
  </div>

  <!-- Editor pages: full chrome -->
  <div v-else class="app-layout">
    <AppHeader />
    <div class="app-main">
      <div v-if="workbook.loading" class="loading-overlay">
        <a-spin size="large" :tip="t('loading')" />
      </div>
      <AppSidebar v-if="!isYamlMode" class="app-sidebar" />
      <div class="app-content" :style="{ zoom: settings.zoom }" @wheel="onContentWheel">
        <router-view />
      </div>
    </div>
    <StatusBar />
  </div>

  <!-- 关闭确认弹窗 / Close confirmation dialog -->
  <a-modal
    v-model:open="closeDialogVisible"
    :title="closeDialogRunningCount > 0 ? t('tray.closeTitle') : t('home.exitConfirmTitle')"
    :footer="null"
    width="440px"
  >
    <!-- 有运行中任务 / Running tasks exist -->
    <template v-if="closeDialogRunningCount > 0">
      <p style="margin-bottom: 16px;">{{ t('tray.closeContent', { count: closeDialogRunningCount }) }}</p>
      <div style="display: flex; gap: 8px; justify-content: flex-end;">
        <a-button @click="closeDialogVisible = false">
          {{ t('dialog.cancel') }}
        </a-button>
        <a-button @click="handleMinimizeToTray">
          {{ t('tray.minimizeToTray') }}
        </a-button>
        <a-button type="primary" danger @click="handleTerminateAndQuit">
          {{ t('tray.terminateAndQuit') }}
        </a-button>
      </div>
    </template>

    <!-- 无运行中任务：简单退出确认 / No running tasks: simple exit confirmation -->
    <template v-else>
      <p style="margin-bottom: 16px;">{{ t('home.exitConfirmContent') }}</p>
      <div style="display: flex; gap: 8px; justify-content: flex-end;">
        <a-button @click="closeDialogVisible = false">
          {{ t('dialog.cancel') }}
        </a-button>
        <a-button type="primary" danger @click="handleForceQuit">
          {{ t('home.exit') }}
        </a-button>
      </div>
    </template>
  </a-modal>
</template>
