<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAgentStore } from '../../stores/agent'
import { openDirectoryDialog } from '../../utils/desktop-bridge'

const { t } = useI18n()
const agent = useAgentStore()

const props = defineProps<{ visible: boolean }>()
const emit = defineEmits<{ 'update:visible': (v: boolean) => void }>()

const local = ref({
  agentRootDir: '',
  configFileName: 'env.yaml',
  pythonExePath: '',
  venvPath: '',
})

watch(() => props.visible, (v) => {
  if (v) {
    local.value = { ...agent.config }
  }
})

async function browseDir() {
  try {
    const dir = await openDirectoryDialog()
    if (dir) local.value.agentRootDir = dir
  } catch { /* user cancelled */ }
}

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
    width="520px"
    @cancel="handleCancel"
  >
    <div class="settings-form">
      <p class="settings-desc">{{ t('agent.settingsDesc') }}</p>

      <div class="settings-field">
        <label>{{ t('agent.settings_agentRootDir') }}</label>
        <a-input-group compact>
          <a-input
            v-model:value="local.agentRootDir"
            style="width: calc(100% - 80px)"
            placeholder="D:\cc_proj\flow-forge\agent"
          />
          <a-button @click="browseDir">{{ t('agent.settings_browse') }}</a-button>
        </a-input-group>
      </div>

      <div class="settings-field">
        <label>{{ t('agent.settings_configFileName') }}</label>
        <a-input v-model:value="local.configFileName" placeholder="env.yaml" />
      </div>

      <div class="settings-field">
        <label>{{ t('agent.settings_pythonExe') }}</label>
        <a-input v-model:value="local.pythonExePath" placeholder="python" />
      </div>

      <div class="settings-field">
        <label>{{ t('agent.settings_venvPath') }}</label>
        <a-input v-model:value="local.venvPath" placeholder=".venv" />
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
  gap: 16px;
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
.settings-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 8px;
}
</style>
