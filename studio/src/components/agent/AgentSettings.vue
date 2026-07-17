<script setup lang="ts">
// AgentSettings — 通用设置模态框，配置 Python/venv + Agent 根目录 + Executor 根目录。
// General settings modal: Python/venv path, Agent root dir, Executor root dir,
// plus env-file sync controls.
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAgentStore } from '../../stores/agent'
import { resolvePythonExe } from '../../utils/resolve-python'
import { openDirectoryDialog, openFileDialog, exists } from '../../utils/desktop-bridge'
import { message } from 'ant-design-vue'

const { t } = useI18n()
const agent = useAgentStore()

const props = defineProps<{ visible: boolean }>()
const emit = defineEmits<{ 'update:visible': (v: boolean) => void }>()

const local = ref({
  pythonExePath: '',
  venvPath: '',
  agentRootDir: '',
  executorRootDir: '',
  saveToEnvFile: false,
  envType: 'system' as 'system' | 'venv' | 'conda',
  condaEnvName: '',
})

// 解析后的 Python 可执行文件路径预览 / Resolved Python executable path preview
const resolvedExe = computed(() => resolvePythonExe(local.value as any))

watch(() => props.visible, (v) => {
  if (v) {
    local.value = { ...agent.config }
  }
})

// ---- 目录选择（含校验）/ Directory browsing with validation ----

async function browseAgentDir() {
  try {
    const dir = await openDirectoryDialog()
    if (!dir) return
    // 校验 main.py 是否存在 / Validate main.py exists
    const mainPy = dir.replace(/\\/g, '/') + '/main.py'
    try {
      const mainExists = await exists(mainPy)
      if (!mainExists) {
        message.warning(t('settings.validationMissingMainPy'))
      }
    } catch { /* 浏览器模式跳过校验 / Skip validation in browser mode */ }
    local.value.agentRootDir = dir
  } catch { /* user cancelled */ }
}

async function browseExecutorDir() {
  try {
    const dir = await openDirectoryDialog()
    if (!dir) return
    // 校验 main.py 和 env.yml 是否存在 / Validate main.py and env.yml exist
    const basePath = dir.replace(/\\/g, '/')
    try {
      const mainExists = await exists(basePath + '/main.py')
      const envExists = await exists(basePath + '/env.yml')
      if (!mainExists) {
        message.warning(t('settings.validationMissingMainPy'))
      }
      if (!envExists) {
        message.warning(t('settings.validationMissingEnvYml'))
      }
    } catch { /* skip in browser */ }
    local.value.executorRootDir = dir
  } catch { /* user cancelled */ }
}

// Python 可执行文件选择 / Python executable file selection
async function browsePythonExe() {
  try {
    const file = await openFileDialog()
    if (!file) return
    // openFileDialog 返回单个路径字符串 / returns single path string
    local.value.pythonExePath = typeof file === 'string' ? file : file[0] || ''
  } catch { /* user cancelled */ }
}

// venv 目录浏览 / Browse venv directory
async function browseVenvDir() {
  try {
    const dir = await openDirectoryDialog()
    if (!dir) return
    local.value.venvPath = dir
  } catch { /* user cancelled */ }
}

// ---- 保存/读取 / Save / Load ----

/**
 * 保存设置到磁盘。
 * Save settings to disk.
 * 失败时弹错误提示，避免静默失败。
 * Shows error on failure instead of silently failing.
 */
async function handleSave() {
  try {
    agent.config = { ...local.value }
    await agent.saveConfig()
    emit('update:visible', false)
  } catch (e: unknown) {
    const err = e as Error
    message.error(t('agent.settings_savedFailed', { reason: err?.message || String(e) }))
  }
}

function handleCancel() {
  emit('update:visible', false)
}
</script>

<template>
  <a-modal
    :open="visible"
    :title="t('agent.settings')"
    :footer="null"
    width="540px"
    @cancel="handleCancel"
  >
    <div class="settings-form">
      <p class="settings-desc">{{ t('agent.settingsDesc') }}</p>

      <!-- Python 环境类型 / Python environment type -->
      <div class="settings-field">
        <label>{{ t('settings.envType') }}</label>
        <a-radio-group v-model:value="local.envType" button-style="solid" size="small">
          <a-radio-button value="system">{{ t('settings.envTypeSystem') }}</a-radio-button>
          <a-radio-button value="venv">{{ t('settings.envTypeVenv') }}</a-radio-button>
          <a-radio-button value="conda">{{ t('settings.envTypeConda') }}</a-radio-button>
        </a-radio-group>
      </div>

      <!-- Python 可执行文件（手动覆盖所有模式）/ Python executable (manual override for all modes) -->
      <div class="settings-field">
        <label>{{ t('agent.settings_pythonExe') }}</label>
        <a-input-group compact>
          <a-input
            v-model:value="local.pythonExePath"
            style="width: calc(100% - 80px)"
            :placeholder="t('settings.pythonExeHint')"
          />
          <a-button @click="browsePythonExe">{{ t('agent.settings_browse') }}</a-button>
        </a-input-group>
      </div>

      <!-- venv 路径（仅 envType=venv 时显示）/ venv path (only when venv selected) -->
      <div v-if="local.envType === 'venv'" class="settings-field">
        <label>{{ t('agent.settings_venvPath') }}</label>
        <a-input-group compact>
          <a-input v-model:value="local.venvPath" style="width: calc(100% - 80px)" :placeholder="t('agent.settings_venvHint')" />
          <a-button @click="browseVenvDir">{{ t('agent.settings_browse') }}</a-button>
        </a-input-group>
      </div>

      <!-- Conda 环境名（仅 envType=conda 时显示）/ Conda env name (only when conda selected) -->
      <div v-if="local.envType === 'conda'" class="settings-field">
        <label>{{ t('settings.condaEnvName') }}</label>
        <a-input v-model:value="local.condaEnvName" :placeholder="t('settings.condaEnvNameHint')" />
        <p class="sync-desc">{{ t('settings.condaAutoResolve') }}</p>
      </div>

      <!-- Python 路径预览 / Python path preview -->
      <div class="path-preview">
        <span class="path-preview-label">{{ t('settings.resolvedExe') }}</span>
        <code class="path-preview-value">{{ resolvedExe }}</code>
      </div>

      <a-divider style="margin: 4px 0" />

      <!-- 智能体根目录 / Agent root directory -->
      <div class="settings-field">
        <label>{{ t('agent.settings_agentRootDir') }}</label>
        <a-input-group compact>
          <a-input
            v-model:value="local.agentRootDir"
            style="width: calc(100% - 80px)"
            :placeholder="t('settings.agentRootDirHint')"
          />
          <a-button @click="browseAgentDir">{{ t('agent.settings_browse') }}</a-button>
        </a-input-group>
      </div>

      <!-- 执行器根目录 / Executor root directory -->
      <div class="settings-field">
        <label>{{ t('settings.executorRootDir') }}</label>
        <a-input-group compact>
          <a-input
            v-model:value="local.executorRootDir"
            style="width: calc(100% - 80px)"
            :placeholder="t('settings.executorRootDirHint')"
          />
          <a-button @click="browseExecutorDir">{{ t('agent.settings_browse') }}</a-button>
        </a-input-group>
      </div>

      <a-divider style="margin: 4px 0" />

      <!-- env 文件同步控制 / Env file sync controls -->
      <div class="settings-field">
        <div class="sync-row">
          <a-switch v-model:checked="local.saveToEnvFile" size="small" />
          <label class="sync-label">{{ t('settings.saveToEnv') }}</label>
        </div>
        <p class="sync-desc">{{ t('settings.saveToEnvHint') }}</p>
      </div>

      <div class="settings-actions">
        <a-button @click="handleCancel">{{ t('dialog.cancel') }}</a-button>
        <a-button type="primary" @click="handleSave">{{ t('agent.form_save') }}</a-button>
      </div>
    </div>
  </a-modal>
</template>

<style scoped>
.settings-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.settings-desc {
  color: #888;
  font-size: 13px;
  margin: 0;
}
.settings-field > label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 4px;
  color: #333;
}
.sync-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.sync-label {
  font-weight: 500;
  color: #333;
  margin-bottom: 0 !important;
}
.sync-desc {
  color: #888;
  font-size: 12px;
  margin: 4px 0 0 0;
}
.settings-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 8px;
}
.path-preview {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 2px 0;
}
.path-preview-label {
  font-size: 12px;
  color: #999;
  white-space: nowrap;
}
.path-preview-value {
  font-size: 12px;
  color: #555;
  background: #f5f5f5;
  padding: 2px 8px;
  border-radius: 3px;
  word-break: break-all;
}

/* Radio 按钮组样式 / Radio button group styling */
.settings-field :deep(.ant-radio-group) {
  display: inline-flex;
  gap: 4px;
}
.settings-field :deep(.ant-radio-button-wrapper) {
  border-radius: 4px;
  transition: all 0.2s;
}
</style>
