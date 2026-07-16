<script setup lang="ts">
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useSettingsStore } from './stores/settings'
import { useWorkbookStore } from './stores/workbook'
import { useYamlStore } from './stores/yaml-store'
import { useAgentStore } from './stores/agent'
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

const isHome = computed(() => route.name === 'home')
const isAnnotator = computed(() => route.name === 'plan-annotator')
const isAgent = computed(() => route.name === 'agent')
const isExecutor = computed(() => route.name === 'executor')
const isConverter = computed(() => route.name === 'converter')
const isYamlMode = computed(() => route.name === 'yaml-editor')

// 关闭确认弹窗状态 / Close confirmation dialog state
const closeDialogVisible = ref(false)
const closeDialogRunningCount = ref(0)

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
  const runningTasks = agent.tasks.filter(
    t => t.status === 'running' || t.status === 'question'
  )
  for (const task of runningTasks) {
    await agent.terminateTask(task.id)
  }
  const { getCurrentWindow } = await import('@tauri-apps/api/window')
  await getCurrentWindow().destroy()
}

onMounted(async () => {
  window.addEventListener('beforeunload', onBeforeUnload)

  // 仅在桌面模式下拦截窗口关闭 / Only intercept in desktop mode
  if (!isDesktop) return

  const { getCurrentWindow } = await import('@tauri-apps/api/window')
  const appWindow = getCurrentWindow()

  appWindow.onCloseRequested(async (event) => {
    const runningTasks = agent.tasks.filter(
      t => t.status === 'running' || t.status === 'question'
    )

    if (runningTasks.length === 0) {
      // 无运行中任务，允许正常关闭 / No running tasks, allow close
      return
    }

    // 阻止关闭，弹出确认对话框 / Prevent close, show dialog
    event.preventDefault()
    closeDialogRunningCount.value = runningTasks.length
    closeDialogVisible.value = true
  })
})

onUnmounted(() => window.removeEventListener('beforeunload', onBeforeUnload))
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
    :title="t('tray.closeTitle')"
    :footer="null"
    width="440px"
  >
    <p style="margin-bottom: 16px;">{{ t('tray.closeContent', { count: closeDialogRunningCount }) }}</p>
    <div style="display: flex; gap: 8px; justify-content: flex-end;">
      <a-button @click="closeDialogVisible = false">
        {{ t('dialog.cancel') }}
      </a-button>
      <a-button danger @click="handleTerminateAndQuit">
        {{ t('tray.terminateAndQuit') }}
      </a-button>
      <a-button type="primary" @click="handleMinimizeToTray">
        {{ t('tray.minimizeToTray') }}
      </a-button>
    </div>
  </a-modal>
</template>
