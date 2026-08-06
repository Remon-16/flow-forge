<script setup lang="ts">
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useSettingsStore } from './stores/settings'
import { useWorkbookStore } from './stores/workbook'
import { useYamlStore } from './stores/yaml-store'
import { useAgentStore } from './stores/agent'
import { useExecutorStore } from './stores/executor'
import { useConverterStore } from './stores/converter'
import { useCounterStore } from './stores/counter'
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
const counterStore = useCounterStore()

// 平台初始化状态 / Platform initialization state
// app.mount 后立即渲染 splash，后台完成平台初始化后切换为正常 UI
// Splash renders immediately after app.mount; switches to normal UI after background platform init completes
const platformReady = ref(false)
const platformError = ref('')

const isHome = computed(() => route.name === 'home')
const isAnnotator = computed(() => route.name === 'plan-annotator')
const isAgent = computed(() => route.name === 'agent')
const isExecutor = computed(() => route.name === 'executor')
const isConverter = computed(() => route.name === 'converter')
const isCounter = computed(() => route.name === 'counter')
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
  // 统一退出入口：kill_all() 会处理所有注册的子进程（含优雅 stdin 通知）
  // Unified exit entry: kill_all() handles all registered subprocesses (incl. graceful stdin notify)
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

  // 后台初始化平台缓存，非阻塞 UI 渲染
  // Initialize platform cache in background, non-blocking UI render
  // 非 Windows 平台守卫在此处理（不影响 UI 显示）
  // Non-Windows guard handled here (does not block UI display)
  const { initPlatformCache } = await import('./utils/resolve-python')
  const { getOsPlatform } = await import('./utils/desktop-bridge')
  try {
    await initPlatformCache()
    const platform = await getOsPlatform()
    if (platform !== 'windows') {
      platformError.value = 'Flow Forge Studio 仅支持 Windows 平台。\n\n请使用命令行工具代替：\n  cd agent && python main.py ...\n  cd python && python main.py ...'
    }
  } catch {
    // 非桌面模式或 IPC 不可用，忽略 / Non-desktop mode or IPC unavailable, ignore
  }

  // 预初始化所有 stores（并行，减少总等待时间）
  // Pre-initialize all stores in parallel to minimize total wait time
  // 用户进入任何页面时数据已在内存中，零延迟渲染
  // Data is ready in memory when user navigates to any page — zero-delay render
  await Promise.all([
    agent.initialize().catch(() => {}),
    executorStore.initialize().catch(() => {}),
    converterStore.initialize().catch(() => {}),
    counterStore.initialize().catch(() => {}),
  ])
  platformReady.value = true

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
      const counterRunning = counterStore.sessions.filter(s => s.status === 'running')
      const totalRunning = agentRunning.length + execRunning.length + convRunning.length + counterRunning.length
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
      const counterRunning2 = counterStore.sessions.filter(s => s.status === 'running')
      const totalRunning2 = agentRunning.length + execRunning.length + convRunning.length + counterRunning2.length
      if (totalRunning2 > 0) {
        closeDialogRunningCount.value = totalRunning2
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
  <!-- 启动加载状态：平台初始化完成前显示 splash，让用户立即看到界面 -->
  <!-- Startup loading state: show splash before platform init completes so user sees UI immediately -->
  <div v-if="!platformReady" class="splash-screen">
    <div class="splash-content">
      <h1>Flow Forge Studio</h1>
      <a-spin />
      <p v-if="platformError" class="splash-error">{{ platformError }}</p>
    </div>
  </div>

  <!-- Home page: no chrome -->
  <div v-else-if="isHome" class="app-layout home-layout">
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

  <!-- Counter diagnostic page: no chrome, standalone -->
  <div v-else-if="isCounter" class="app-layout counter-layout">
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

<style scoped>
/* 启动加载 Splash 屏幕 / Startup splash screen
   在平台初始化完成前显示，避免用户看到空白页面。
   Displayed before platform init completes to avoid blank page. */
.splash-screen {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100vh;
  width: 100vw;
  background: #f5f5f5;
}
.splash-content {
  text-align: center;
}
.splash-content h1 {
  font-size: 24px;
  margin-bottom: 16px;
  color: #333;
  font-weight: 600;
}
.splash-error {
  color: #ff4d4f;
  margin-top: 12px;
  white-space: pre-line;
  font-size: 13px;
}
</style>
