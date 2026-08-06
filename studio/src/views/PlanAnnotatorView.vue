<script setup lang="ts">
/** 独立批注器页面 / Standalone annotator page.
    使用 AnnotatorPanel 组件，自身负责目录选择和页面级 toolbar。
    Uses AnnotatorPanel; handles directory selection and page-level toolbar.
*/

import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import AnnotatorPanel from '../components/annotator/AnnotatorPanel.vue'
import { openDirectoryDialog, readFile, exists, isDesktop } from '../utils/desktop-bridge'
import { useSettingsStore } from '../stores/settings'
import { joinPath } from '../utils/path-utils'

const router = useRouter()
const { t } = useI18n()
const settings = useSettingsStore()

const directoryPath = ref('')
const planContent = ref('')
const loading = ref(false)

const zoomPercent = computed(() => Math.round(settings.zoom * 100) + '%')

async function openDirectory() {
  if (!isDesktop) {
    message.warning('请在桌面应用中打开目录。')
    return
  }
  try {
    const dir = await openDirectoryDialog()
    if (!dir) return
    loading.value = true
    directoryPath.value = dir

    const planMdPath = joinPath(dir, 'plan.md')
    if (!(await exists(planMdPath))) {
      message.error(t('annotator.noPlan'))
      loading.value = false
      return
    }
    planContent.value = await readFile(planMdPath)
    loading.value = false
  } catch (e: any) {
    message.error(e?.message || 'Failed to open directory')
    loading.value = false
  }
}

function handleLanguageChange(lang: string) {
  settings.setLanguage(lang as 'zh-CN' | 'en-US')
}

function zoomIn() { settings.zoomIn() }
function zoomOut() { settings.zoomOut() }
function zoomReset() { settings.zoomReset() }

function goBack() {
  router.push('/')
}

// Keyboard shortcuts
function onKeyDown(e: KeyboardEvent) {
  if (e.ctrlKey && (e.key === '=' || e.key === '+')) {
    e.preventDefault(); settings.zoomIn()
  } else if (e.ctrlKey && e.key === '-') {
    e.preventDefault(); settings.zoomOut()
  } else if (e.ctrlKey && e.key === '0') {
    e.preventDefault(); settings.zoomReset()
  }
}

onMounted(() => window.addEventListener('keydown', onKeyDown))
onUnmounted(() => window.removeEventListener('keydown', onKeyDown))
</script>

<template>
  <div class="plan-annotator">
    <!-- Toolbar -->
    <div class="annotator-toolbar">
      <a-button @click="goBack" size="small">
        ← {{ t('header.backHome') }}
      </a-button>
      <span class="toolbar-title">{{ t('annotator.title') }}</span>

      <a-button size="small" @click="zoomOut" :disabled="settings.zoom <= 0.5" title="Ctrl+-">−</a-button>
      <span class="zoom-label">{{ zoomPercent }}</span>
      <a-button size="small" @click="zoomIn" :disabled="settings.zoom >= 2.0" title="Ctrl+=">+</a-button>
      <a-button size="small" @click="zoomReset" :disabled="settings.zoom === 1" title="Ctrl+0">⟲</a-button>

      <a-button
        size="small"
        :type="settings.showLineNumbers ? 'primary' : 'default'"
        @click="settings.toggleLineNumbers()"
      >
        {{ t('annotator.lineNumbers') }}
      </a-button>

      <a-select
        :value="settings.language"
        size="small"
        style="width: 90px"
        @change="handleLanguageChange"
      >
        <a-select-option value="zh-CN">中文</a-select-option>
        <a-select-option value="en-US">English</a-select-option>
      </a-select>
      <a-button type="primary" size="small" @click="openDirectory">
        {{ t('annotator.openDir') }}
      </a-button>
    </div>

    <!-- Main content -->
    <div class="annotator-main">
      <!-- Loading state -->
      <div v-if="loading" class="annotator-loading">
        <a-spin size="large" />
      </div>

      <!-- Empty state -->
      <div v-else-if="!planContent" class="annotator-empty">
        <div class="empty-icon">📋</div>
        <div class="empty-text">{{ t('annotator.noPlan') }}</div>
        <a-button type="primary" @click="openDirectory">
          {{ t('annotator.openDir') }}
        </a-button>
      </div>

      <!-- Annotator -->
      <AnnotatorPanel
        v-else
        :memory-dir="directoryPath"
        :show-toolbar="false"
      />
    </div>
  </div>
</template>

<style scoped>
.plan-annotator {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.annotator-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  border-bottom: 1px solid #e8e8e8;
  background: #fff;
  flex-shrink: 0;
}
.toolbar-title {
  flex: 1;
  font-size: 14px;
  font-weight: 600;
  color: #333;
}
.zoom-label {
  font-size: 12px;
  min-width: 40px;
  text-align: center;
  color: #666;
  user-select: none;
}
.annotator-main {
  flex: 1;
  display: flex;
  overflow: hidden;
}
.annotator-loading {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}
.annotator-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
}
.empty-icon { font-size: 48px; opacity: 0.5; }
.empty-text { font-size: 16px; color: #999; }
</style>
