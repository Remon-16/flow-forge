<script setup lang="ts">
// ConverterForm — 转换前配置表单。
// Pre-conversion config form: direction selector, input/output paths.
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useConverterStore } from '../../stores/converter'
import { useAgentStore } from '../../stores/agent'
import { CONVERTER_DIRECTIONS, type ConverterDirection } from '../../types/converter'
import { openFileDialog, openDirectoryDialog } from '../../utils/desktop-bridge'
import { message } from 'ant-design-vue'

const { t } = useI18n()
const converter = useConverterStore()
const agent = useAgentStore()

const direction = ref<ConverterDirection>('excel2yaml')
const inputPath = ref('')
const outputPath = ref('')
const interfacesDir = ref('')
const singleCasesDir = ref('')
const bizFlowsDir = ref('')
const configDir = ref('')
const processorsDir = ref('')

// 是否显示 yaml 输入字段 / Whether to show YAML input fields
const isYamlInput = ref(false)
const isPytest = ref(false)

function onDirectionChange(val: ConverterDirection) {
  isYamlInput.value = val === 'yaml2excel' || val === 'yaml2pytest'
  isPytest.value = val === 'yaml2pytest' || val === 'excel2pytest'
}

async function browseInputFile() {
  try {
    const result = await openFileDialog([{ name: 'Excel', extensions: ['xlsx', 'xls'] }])
    if (result) inputPath.value = Array.isArray(result) ? result[0] : result
  } catch { /* cancelled */ }
}

async function browseOutputDir() {
  try {
    const dir = await openDirectoryDialog()
    if (dir) outputPath.value = dir
  } catch { /* cancelled */ }
}

async function browseOutputFile() {
  try {
    const result = await openFileDialog([{ name: 'Excel', extensions: ['xlsx'] }])
    if (result) outputPath.value = Array.isArray(result) ? result[0] : result
  } catch { /* cancelled */ }
}

async function browseDir(field: 'interfaces' | 'singleCases' | 'bizFlows' | 'config' | 'processors') {
  try {
    const dir = await openDirectoryDialog()
    if (!dir) return
    switch (field) {
      case 'interfaces': interfacesDir.value = dir; break
      case 'singleCases': singleCasesDir.value = dir; break
      case 'bizFlows': bizFlowsDir.value = dir; break
      case 'config': configDir.value = dir; break
      case 'processors': processorsDir.value = dir; break
    }
  } catch { /* cancelled */ }
}

async function handleSubmit() {
  if (!agent.config.agentRootDir) {
    message.warning(t('converter.noRootDir'))
    return
  }

  const sessionId = converter.createSession({
    direction: direction.value,
    inputPath: inputPath.value,
    outputPath: outputPath.value,
    interfacesDir: interfacesDir.value,
    singleCasesDir: singleCasesDir.value,
    bizFlowsDir: bizFlowsDir.value,
    configDir: configDir.value,
    processorsDir: processorsDir.value,
  })

  await converter.startSession(sessionId)
}
</script>

<template>
  <div class="form">
    <!-- 转换方向 / Direction -->
    <div class="form-section">
      <label class="section-title">{{ t('converter.form_direction') }}</label>
      <a-select
        v-model:value="direction"
        style="width: 240px"
        @change="onDirectionChange"
      >
        <a-select-option
          v-for="d in CONVERTER_DIRECTIONS"
          :key="d.value"
          :value="d.value"
        >
          {{ d.label }}
        </a-select-option>
      </a-select>
    </div>

    <!-- 输入字段 / Input fields -->
    <div class="form-section">
      <span class="section-title">{{ t('converter.form_input') }}</span>

      <!-- Excel input -->
      <div v-if="!isYamlInput" class="param-row">
        <label>{{ t('converter.param_inputFile') }}</label>
        <a-input-group compact>
          <a-input v-model:value="inputPath" style="width: calc(100% - 80px)" />
          <a-button @click="browseInputFile">{{ t('agent.settings_browse') }}</a-button>
        </a-input-group>
      </div>

      <!-- YAML input dirs -->
      <template v-if="isYamlInput">
        <div class="param-row">
          <label>{{ t('converter.param_interfaces') }}</label>
          <a-input-group compact>
            <a-input v-model:value="interfacesDir" style="width: calc(100% - 80px)" />
            <a-button @click="browseDir('interfaces')">{{ t('agent.settings_browse') }}</a-button>
          </a-input-group>
        </div>
        <div class="param-row">
          <label>{{ t('converter.param_singleCases') }}</label>
          <a-input-group compact>
            <a-input v-model:value="singleCasesDir" style="width: calc(100% - 80px)" />
            <a-button @click="browseDir('singleCases')">{{ t('agent.settings_browse') }}</a-button>
          </a-input-group>
        </div>
        <div class="param-row">
          <label>{{ t('converter.param_bizFlows') }}</label>
          <a-input-group compact>
            <a-input v-model:value="bizFlowsDir" style="width: calc(100% - 80px)" />
            <a-button @click="browseDir('bizFlows')">{{ t('agent.settings_browse') }}</a-button>
          </a-input-group>
        </div>
      </template>

      <!-- pytest extra dirs -->
      <template v-if="isPytest">
        <div class="param-row">
          <label>{{ t('converter.param_configDir') }}</label>
          <a-input-group compact>
            <a-input v-model:value="configDir" style="width: calc(100% - 80px)" />
            <a-button @click="browseDir('config')">{{ t('agent.settings_browse') }}</a-button>
          </a-input-group>
        </div>
        <div class="param-row">
          <label>{{ t('converter.param_processorsDir') }}</label>
          <a-input-group compact>
            <a-input v-model:value="processorsDir" style="width: calc(100% - 80px)" />
            <a-button @click="browseDir('processors')">{{ t('agent.settings_browse') }}</a-button>
          </a-input-group>
        </div>
      </template>
    </div>

    <!-- 输出字段 / Output -->
    <div class="form-section">
      <span class="section-title">{{ t('converter.form_output') }}</span>
      <div class="param-row">
        <label>{{ t('converter.param_output') }}</label>
        <a-input-group compact>
          <a-input v-model:value="outputPath" style="width: calc(100% - 80px)" />
          <a-button
            v-if="isYamlInput"
            @click="browseOutputDir"
          >{{ t('agent.settings_browse') }}</a-button>
          <a-button
            v-else-if="direction === 'excel2yaml' || direction === 'yaml2pytest'"
            @click="browseOutputDir"
          >{{ t('agent.settings_browse') }}</a-button>
          <a-button
            v-else
            @click="browseOutputFile"
          >{{ t('agent.settings_browse') }}</a-button>
        </a-input-group>
      </div>
    </div>

    <!-- Submit -->
    <div class="form-footer">
      <a-button type="primary" size="large" block @click="handleSubmit">
        ⟳ {{ t('converter.form_submit') }}
      </a-button>
    </div>
  </div>
</template>

<style scoped>
.form {
  padding: 24px;
  overflow-y: auto;
  height: 100%;
  display: flex;
  flex-direction: column;
}
.form-section {
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid #f0f0f0;
}
.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #333;
  display: block;
  margin-bottom: 8px;
}
.param-row {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-bottom: 8px;
}
.param-row label {
  font-size: 12px;
  color: #666;
}
.form-footer {
  margin-top: auto;
  padding-top: 16px;
}
</style>
