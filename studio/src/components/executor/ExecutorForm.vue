<script setup lang="ts">
// ExecutorForm — 执行前配置表单。
// Pre-execution config form: env suffix selection, Block1 (env-only) + Block2 (CLI params).
import { ref, watch, onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useExecutorStore } from '../../stores/executor'
import { useAgentStore } from '../../stores/agent'
import { DEFAULT_CLI_PARAMS } from '../../types/executor'
import type { ExecutorCliParams } from '../../types/executor'
import { openFileDialog, openDirectoryDialog } from '../../utils/desktop-bridge'
import yaml from 'js-yaml'
import { message } from 'ant-design-vue'
import JsonEditor from '../json-editor/JsonEditor.vue'

const { t } = useI18n()
const executor = useExecutorStore()
const agent = useAgentStore()

// 环境后缀列表 / Env suffix list
const envSuffixes = ref<string[]>([''])
const selectedSuffix = ref('')

// Block1: env-only params
const envOnlyParams = ref<Record<string, unknown>>({})

// Block2: CLI params
const cliParams = ref<ExecutorCliParams>({ ...DEFAULT_CLI_PARAMS })

// 用例文件 / Case file paths
const caseFilePath = ref('')
const yamlDir = ref('')
const yamlFiles = ref('')

// 加载中 / Loading
const loading = ref(false)

/** 去除 _app_ 前缀用于显示 / Strip _app_ prefix for display */
function stripAppPrefix(data: Record<string, unknown>): Record<string, unknown> {
  const result: Record<string, unknown> = {}
  for (const [key, val] of Object.entries(data)) {
    result[key.startsWith('_app_') ? key.slice(5) : key] = val
  }
  return result
}

// 用于显示的 env-only 参数（去 _app_ 前缀）/ Env-only params for display (without _app_ prefix)
const envOnlyParamsForDisplay = computed(() => stripAppPrefix(envOnlyParams.value))

// ---- YAML 原文编辑（始终可编辑，自动弱校验）/ YAML raw text editing (always editable, auto subtle validation) ----

const envYamlText = ref('')
const envYamlError = ref('')
const showFullEnvEditor = ref(false)

/** 从数据模型同步 YAML 文本 / Sync YAML text from data model */
function syncEnvYamlFromData() {
  envYamlText.value = yaml.dump(envOnlyParamsForDisplay.value, {
    indent: 2, lineWidth: -1, noRefs: true, sortKeys: false,
  })
  envYamlError.value = ''
}

/** 自动校验 YAML 语法（弱提示）/ Auto-validate YAML syntax (subtle hint) */
function autoValidateEnvYaml() {
  if (!envYamlText.value.trim()) {
    envYamlError.value = ''
    return
  }
  try {
    yaml.load(envYamlText.value)
    envYamlError.value = ''
  } catch (e: any) {
    envYamlError.value = e?.message || String(e)
  }
}

/** 应用 YAML 原文编辑 → 解析并更新数据模型 / Apply YAML raw edit → parse and update data model */
function applyEnvYamlEdit() {
  // 空 textarea → 清空所有 env-only 参数 / Empty textarea → clear all env-only params
  if (!envYamlText.value.trim()) {
    envOnlyParams.value = {}
    syncEnvYamlFromData()
    return
  }
  // 有语法错误时不应用（弱提示已显示给用户）/ Don't apply when syntax error (subtle hint already shown)
  if (envYamlError.value) return
  try {
    const parsed = yaml.load(envYamlText.value) as Record<string, unknown>
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return
    // 重新添加 _app_ 前缀给嵌套对象（与 store 的 flattenEnvConfig 保持一致，确保向后兼容）
    // Re-add _app_ prefix for nested objects (consistent with store's flattenEnvConfig for backward compat)
    const result: Record<string, unknown> = {}
    for (const [key, val] of Object.entries(parsed)) {
      if (typeof val === 'object' && val !== null && !Array.isArray(val)) {
        result[`_app_${key}`] = val
      } else {
        result[key] = val
      }
    }
    envOnlyParams.value = result
    syncEnvYamlFromData()
  } catch { /* 语法错误时不做任何事 / do nothing on syntax error */ }
}

/** JsonEditor 确认回调 — 更新数据模型并刷新 textarea / JsonEditor confirm — update data model and refresh textarea */
function onEnvEditorConfirm(value: Record<string, unknown>) {
  const result: Record<string, unknown> = {}
  for (const [key, val] of Object.entries(value)) {
    if (typeof val === 'object' && val !== null && !Array.isArray(val)) {
      result[`_app_${key}`] = val
    } else {
      result[key] = val
    }
  }
  envOnlyParams.value = result
  showFullEnvEditor.value = false
  syncEnvYamlFromData()
}

// 初始化 YAML 文本 / Initialize YAML text
syncEnvYamlFromData()

onMounted(async () => {
  loading.value = true
  try {
    envSuffixes.value = await executor.readEnvSuffixes()
    if (envSuffixes.value.length > 0) {
      selectedSuffix.value = envSuffixes.value[0]
      await loadEnvData()
    }
  } finally {
    loading.value = false
  }
})

// 环境切换时重新加载 / Reload when suffix changes
watch(selectedSuffix, async () => {
  await loadEnvData()
})

// 监听 agent config 中 executorRootDir 的变化，路径变更后重新扫描 env 文件
// Watch executorRootDir changes in agent config; re-scan env files when path changes
watch(() => agent.config.executorRootDir, async (newVal, oldVal) => {
  if (newVal && newVal !== oldVal) {
    loading.value = true
    try {
      envSuffixes.value = await executor.readEnvSuffixes()
      if (envSuffixes.value.length > 0) {
        selectedSuffix.value = envSuffixes.value[0]
        await loadEnvData()
      }
    } finally {
      loading.value = false
    }
  }
})

async function loadEnvData() {
  try {
    const data = await executor.readEnvFile(selectedSuffix.value)
    // 分离 Block1 (env-only) 和 Block2 (CLI available) 参数
    // Separate Block1 (env-only) and Block2 (CLI available) params
    const cliKeys = ['scriptType', 'maxThread', 'reportName', 'apiMode', 'caseFilePath']
    const block1: Record<string, unknown> = {}
    const block2: Partial<ExecutorCliParams> = {}

    for (const [key, val] of Object.entries(data)) {
      if (key.startsWith('_app_')) {
        block1[key] = val
      } else if (cliKeys.includes(key)) {
        ;(block2 as Record<string, unknown>)[key] = val
      } else if (key !== 'lang' && key !== 'excel_font') {
        block1[key] = val
      }
    }

    envOnlyParams.value = block1
    syncEnvYamlFromData()
    cliParams.value = {
      scriptType: (block2.scriptType as string) || DEFAULT_CLI_PARAMS.scriptType,
      maxThread: Number(block2.maxThread) || DEFAULT_CLI_PARAMS.maxThread,
      reportName: (block2.reportName as string) || DEFAULT_CLI_PARAMS.reportName,
      apiMode: (block2.apiMode as string) || DEFAULT_CLI_PARAMS.apiMode,
    }

    const cfp = data['caseFilePath']
    if (cfp && typeof cfp === 'string') caseFilePath.value = cfp
  } catch (e: unknown) {
    const err = e as Error
    message.error(t('executor.envLoadFailed', { reason: err?.message || String(e) }))
    envOnlyParams.value = {}
  }
}

// ---- File browsing / 文件浏览 ----

async function browseCaseFile() {
  try {
    const result = await openFileDialog([{ name: 'Excel', extensions: ['xlsx', 'xls'] }])
    if (result) caseFilePath.value = Array.isArray(result) ? result[0] : result
  } catch { /* cancelled */ }
}

async function browseYamlDir() {
  try {
    const dir = await openDirectoryDialog()
    if (dir) yamlDir.value = dir
  } catch { /* cancelled */ }
}

// ---- Save env / 保存 env ----

async function handleSaveEnv() {
  try {
    // 先应用 textarea 中的 YAML 编辑 / Apply YAML edits from textarea first
    applyEnvYamlEdit()
    await executor.writeEnvFile(selectedSuffix.value, envOnlyParams.value)
    message.success(t('executor.envSaved'))
  } catch (e: unknown) {
    const err = e as Error
    message.error(t('executor.envSaveFailed', { reason: err?.message || String(e) }))
  }
}

// ---- Submit / 提交 ----

async function handleSubmit() {
  if (!agent.config.executorRootDir) {
    message.warning(t('executor.noExecutorRoot'))
    return
  }

  // 先应用 textarea 中的 YAML 编辑 / Apply YAML edits from textarea first
  applyEnvYamlEdit()

  // Block1 (env-only) 始终写入 / Always write Block1
  await executor.writeEnvFile(selectedSuffix.value, envOnlyParams.value)

  // Block2 (CLI) 根据同步开关决定是否写 env / Sync Block2 based on toggle
  if (agent.config.saveToEnvFile) {
    const cliForEnv: Record<string, unknown> = {
      scriptType: cliParams.value.scriptType,
      maxThread: cliParams.value.maxThread,
      reportName: cliParams.value.reportName,
      apiMode: cliParams.value.apiMode,
    }
    if (caseFilePath.value) cliForEnv['caseFilePath'] = caseFilePath.value
    await executor.writeEnvFile(selectedSuffix.value, { ...envOnlyParams.value, ...cliForEnv })
  }

  const sessionId = executor.createSession({
    envSuffix: selectedSuffix.value,
    caseFilePath: caseFilePath.value,
    yamlDir: yamlDir.value,
    yamlFiles: yamlFiles.value,
    envOnlyParams: { ...envOnlyParams.value },
    cliParams: { ...cliParams.value },
  })

  await executor.startSession(sessionId)
}
</script>

<template>
  <div class="form">
    <a-spin :spinning="loading">
      <!-- 环境选择 / Env selection -->
      <div class="form-section">
        <label class="section-title">{{ t('executor.form_envSuffix') }}</label>
        <a-select v-model:value="selectedSuffix" style="width: 200px">
          <a-select-option v-for="s in envSuffixes" :key="s" :value="s">
            {{ s || 'env.yml (default)' }}
          </a-select-option>
        </a-select>
      </div>

      <!-- Block 1: env-only 参数 / Env-only params -->
      <div class="form-section">
        <div class="block-header">
          <span class="section-title">{{ t('executor.form_block1Title') }}</span>
          <a-tag color="red">{{ t('executor.form_envOnly') }}</a-tag>
        </div>
        <p class="section-desc">{{ t('executor.form_block1Desc') }}</p>

        <!-- YAML 原文编辑（始终可编辑，自动弱校验）/ YAML raw text editing (always editable, auto subtle validation) -->
        <div class="env-yaml-edit-area">
          <a-textarea
            v-model:value="envYamlText"
            :rows="12"
            style="font-family: monospace; font-size: 13px;"
            @change="autoValidateEnvYaml"
          />
          <div v-if="envYamlError" class="yaml-hint">
            ⚠ {{ envYamlError }}
          </div>
          <div class="env-yaml-actions">
            <a-button size="small" @click="handleSaveEnv">
              {{ t('executor.form_saveEnv') }}
            </a-button>
            <a-button size="small" @click="showFullEnvEditor = true">
              {{ t('jsonEditor.editDetails') }}
            </a-button>
          </div>
        </div>

        <!-- JsonEditor 弹窗（可视化编辑）/ JsonEditor modal (visual editing) -->
        <JsonEditor
          :visible="showFullEnvEditor"
          :value="envOnlyParamsForDisplay"
          :title="t('executor.form_block1Title')"
          @confirm="onEnvEditorConfirm"
          @cancel="showFullEnvEditor = false"
        />
      </div>

      <!-- Block 2: CLI 参数 / CLI params -->
      <div class="form-section">
        <span class="section-title">{{ t('executor.form_block2Title') }}</span>
        <p class="section-desc">{{ t('executor.form_block2Desc') }}</p>

        <div class="param-grid">
          <div class="param-row">
            <label>{{ t('executor.param_scriptType') }}</label>
            <a-input v-model:value="cliParams.scriptType" />
          </div>
          <div class="param-row">
            <label>{{ t('executor.param_maxThread') }}</label>
            <a-input-number v-model:value="cliParams.maxThread" :min="1" :max="50" />
          </div>
          <div class="param-row">
            <label>{{ t('executor.param_reportName') }}</label>
            <a-input v-model:value="cliParams.reportName" />
          </div>
          <div class="param-row">
            <label>{{ t('executor.param_apiMode') }}</label>
            <a-select v-model:value="cliParams.apiMode" style="width: 120px">
              <a-select-option value="all">{{ t('agent.config_both') }}</a-select-option>
              <a-select-option value="single">{{ t('agent.config_single') }}</a-select-option>
              <a-select-option value="biz">{{ t('agent.config_biz') }}</a-select-option>
            </a-select>
          </div>
        </div>

        <div class="param-row" style="margin-top: 8px">
          <label>{{ t('executor.param_caseFilePath') }}</label>
          <a-input-group compact>
            <a-input v-model:value="caseFilePath" style="width: calc(100% - 80px)" />
            <a-button @click="browseCaseFile">{{ t('agent.settings_browse') }}</a-button>
          </a-input-group>
        </div>
        <div class="param-row" style="margin-top: 8px">
          <label>{{ t('executor.param_yamlDir') }}</label>
          <a-input-group compact>
            <a-input v-model:value="yamlDir" style="width: calc(100% - 80px)" />
            <a-button @click="browseYamlDir">{{ t('agent.settings_browse') }}</a-button>
          </a-input-group>
        </div>
        <div class="param-row" style="margin-top: 8px">
          <label>{{ t('executor.param_yamlFiles') }}</label>
          <a-input v-model:value="yamlFiles" placeholder="file1.yaml,file2.yaml" />
        </div>

        <a-button type="text" size="small" @click="loadEnvData" style="margin-top: 8px">
          {{ t('settings.readFromEnv') }}
        </a-button>
      </div>
    </a-spin>

    <!-- 提交 / Submit -->
    <div class="form-footer">
      <a-button type="primary" size="large" block @click="handleSubmit">
        ▶ {{ t('executor.form_submit') }}
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
}
.section-desc {
  font-size: 12px;
  color: #999;
  margin: 4px 0 8px 0;
}
/* YAML 原文编辑（始终可编辑）/ YAML raw text editing (always editable) */
.env-yaml-edit-area {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.env-yaml-actions {
  display: flex;
  gap: 8px;
}
.yaml-hint {
  color: #faad14;
  font-size: 12px;
}
.block-header {
  display: flex;
  align-items: center;
  gap: 8px;
}
.param-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.param-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.param-row {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.param-row label {
  font-size: 12px;
  color: #666;
}
/* 嵌套对象组 / Nested object group */
.param-group {
  margin-top: 4px;
  padding: 8px;
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  background: #fafafa;
}
.group-label {
  font-size: 12px;
  font-weight: 600;
  color: #555;
  display: block;
  margin-bottom: 6px;
}
.group-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}
.param-row-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.param-row-header label {
  font-size: 12px;
  color: #666;
  margin-bottom: 0;
}
.indent-group {
  margin-left: 6px;
  margin-top: 4px;
}
.indent-row {
  margin-left: 12px;
}
/* 只读参数值 / Readonly param value */
.param-value-readonly {
  font-size: 12px;
  color: #999;
  padding: 4px 8px;
  background: #f5f5f5;
  border-radius: 3px;
  word-break: break-all;
}
.form-footer {
  margin-top: auto;
  padding-top: 16px;
}
</style>
