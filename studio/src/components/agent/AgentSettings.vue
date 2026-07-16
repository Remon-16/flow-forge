<script setup lang="ts">
// AgentSettings — 通用设置模态框，配置 Python/venv + Agent 根目录 + Executor 根目录。
// General settings modal: Python/venv path, Agent root dir, Executor root dir,
// plus env-file sync controls.
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAgentStore } from '../../stores/agent'
import { openDirectoryDialog, exists } from '../../utils/desktop-bridge'
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
})

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

// ---- 保存/读取 / Save / Load ----

async function handleSave() {
  agent.config = { ...local.value }
  await agent.saveConfig()
  emit('update:visible', false)
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

      <!-- Python 可执行文件 / Python executable -->
      <div class="settings-field">
        <label>{{ t('agent.settings_pythonExe') }}</label>
        <a-input v-model:value="local.pythonExePath" placeholder="python" />
      </div>

      <!-- 虚拟环境路径 / Virtual env path -->
      <div class="settings-field">
        <label>{{ t('agent.settings_venvPath') }}</label>
        <a-input v-model:value="local.venvPath" placeholder=".venv" />
      </div>

      <a-divider style="margin: 4px 0" />

      <!-- 智能体根目录 / Agent root directory -->
      <div class="settings-field">
        <label>{{ t('agent.settings_agentRootDir') }}</label>
        <a-input-group compact>
          <a-input
            v-model:value="local.agentRootDir"
            style="width: calc(100% - 80px)"
            placeholder="D:\cc_proj\flow-forge\agent"
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
            placeholder="D:\cc_proj\flow-forge\python"
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
.settings-field label {
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
</style>
