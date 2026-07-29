<script setup lang="ts">
// ParamEditModal — 参数编辑模态框（从编辑器工具栏触发）。
// Parameter edit modal for editor toolbar — edit run/convert params.
import { ref, watch, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useExecutorStore } from '../../stores/executor'
import { useAgentStore } from '../../stores/agent'
import { DEFAULT_CLI_PARAMS, type ExecutorCliParams } from '../../types/executor'
import { useConverterStore } from '../../stores/converter'
import { CONVERTER_DIRECTIONS } from '../../types/converter'
import type { ConverterDirection } from '../../types/converter'
import yaml from 'js-yaml'
import JsonEditor from '../json-editor/JsonEditor.vue'
import { openFileDialog, openDirectoryDialog } from '../../utils/desktop-bridge'
import { message } from 'ant-design-vue'

const { t } = useI18n()
const executor = useExecutorStore()
const converter = useConverterStore()
const agent = useAgentStore()

const props = defineProps<{
  visible: boolean
  /** 'executor' | 'converter' */
  mode: 'executor' | 'converter'
  /** 编辑器文件路径（用于参数持久化 key） / Editor file path (for persistence key) */
  filePath?: string
}>()

const emit = defineEmits<{
  'update:visible': [v: boolean]
}>()

// CLI params
const cliParams = ref<ExecutorCliParams>({ ...DEFAULT_CLI_PARAMS })

// 是否有 env-only 参数（executor mode 才显示）/ Whether to show env-only params
const isExecutor = computed(() => props.mode === 'executor')

// 是否已加载 / Has loaded
const loaded = ref(false)

// Converter mode state / 转换器模式状态
const converterDirection = ref<ConverterDirection>('excel2yaml')
const converterInputPath = ref('')
const converterOutputPath = ref('')

// Env-only params (for executor mode only)
const envOnlyParams = ref<Record<string, unknown>>({})
const selectedSuffix = ref('')

// 环境后缀列表（executor 模式）/ Env suffix list (executor mode)
const envSuffixes = ref<string[]>([''])

// YAML 编辑状态 / YAML editing state
const envYamlText = ref('')
const envYamlError = ref('')
const showFullEnvEditor = ref(false)

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

watch(() => props.visible, async (v) => {
  if (!v) return

  // 从 store 加载上次保存的参数 / Load last saved params from store
  const saved = executor.getEditorCliParams(props.filePath || '__default__')
  cliParams.value = { ...saved }

  // 如果是 executor 模式，加载 env 数据 / Load env data for executor mode
  if (isExecutor.value) {
    const suffixes = await executor.readEnvSuffixes()
    envSuffixes.value = suffixes
    selectedSuffix.value = suffixes[0] || ''
    if (selectedSuffix.value) {
      const raw = await executor.readEnvFile(selectedSuffix.value)
      // 过滤 CLI 键，仅保留 env-only 参数 / Filter CLI keys, keep only env-only params
      const cliKeys = ['scriptType', 'maxThread', 'reportName', 'apiMode', 'caseFilePath']
      const filtered: Record<string, unknown> = {}
      for (const [key, val] of Object.entries(raw)) {
        if (key.startsWith('_app_')) {
          filtered[key] = val
        } else if (!cliKeys.includes(key) && key !== 'lang' && key !== 'excel_font') {
          filtered[key] = val
        }
      }
      envOnlyParams.value = filtered
      syncEnvYamlFromData()
    }
  } else {
    // Converter 模式：从 store 加载保存的参数 / Converter mode: load saved params from store
    const saved = converter.getEditorConverterParams(props.filePath || '__default__')
    converterDirection.value = saved.direction
    converterInputPath.value = props.filePath || ''
    converterOutputPath.value = saved.outputPath || ''
  }

  loaded.value = true
})

// 环境切换时重新加载 env 数据 / Reload env data when suffix changes
watch(selectedSuffix, async (newVal) => {
  if (!newVal || !isExecutor.value || !loaded.value) return
  const raw = await executor.readEnvFile(newVal)
  const cliKeys = ['scriptType', 'maxThread', 'reportName', 'apiMode', 'caseFilePath']
  const filtered: Record<string, unknown> = {}
  for (const [key, val] of Object.entries(raw)) {
    if (key.startsWith('_app_')) {
      filtered[key] = val
    } else if (!cliKeys.includes(key) && key !== 'lang' && key !== 'excel_font') {
      filtered[key] = val
    }
  }
  envOnlyParams.value = filtered
  syncEnvYamlFromData()
})

// ---- YAML 编辑函数（复用 ExecutorForm 模式）/ YAML editing functions (reuse ExecutorForm pattern) ----

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
    // 重新添加 _app_ 前缀给嵌套对象 / Re-add _app_ prefix for nested objects
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

/** 保存 env 到文件 / Save env to file */
async function handleSaveEnv() {
  applyEnvYamlEdit()
  try {
    await executor.writeEnvFile(selectedSuffix.value, envOnlyParams.value)
    message.success(t('executor.envSaved'))
  } catch (e: unknown) {
    const err = e as Error
    message.error(t('executor.envSaveFailed', { reason: err?.message || String(e) }))
  }
}

// ---- Converter 辅助函数 / Converter helper functions ----

/** 浏览输出文件（Excel 方向）/ Browse output file (Excel direction) */
async function browseConverterOutputFile() {
  try {
    const result = await openFileDialog([{ name: 'Excel', extensions: ['xlsx'] }])
    if (result) converterOutputPath.value = Array.isArray(result) ? result[0] : result
  } catch { /* cancelled */ }
}

/** 浏览输出目录（YAML 方向）/ Browse output directory (YAML direction) */
async function browseConverterOutputDir() {
  try {
    const dir = await openDirectoryDialog()
    if (dir) converterOutputPath.value = dir
  } catch { /* cancelled */ }
}

/** 转换方向是否为 YAML 输出 / Whether direction outputs YAML */
const isConverterYamlOutput = computed(() =>
  converterDirection.value === 'excel2yaml' || converterDirection.value === 'excel2pytest' || converterDirection.value === 'yaml2pytest'
)

/**
 * 保存参数到 store 并写入 env 文件。
 * Save params to store and write to env file.
 * 异步等待写入完成后再关闭模态框，失败时弹错误提示。
 * Awaits write completion before closing; shows error on failure.
 */
async function handleSave() {
  // 先应用 textarea 中的 YAML 编辑 / Apply YAML edits from textarea first
  if (isExecutor.value) {
    applyEnvYamlEdit()
  }

  // 保存 CLI 参数到 store / Save CLI params to store
  executor.setEditorCliParams(props.filePath || '__default__', { ...cliParams.value })

  // 构建完整 env 数据，根据同步开关决定是否包含 CLI 参数 / Build complete env data
  if (isExecutor.value && selectedSuffix.value) {
    let envData: Record<string, unknown> = { ...envOnlyParams.value }
    if (agent.config.saveToEnvFile) {
      const cliForEnv: Record<string, unknown> = {
        scriptType: cliParams.value.scriptType,
        maxThread: cliParams.value.maxThread,
        reportName: cliParams.value.reportName,
        apiMode: cliParams.value.apiMode,
      }
      envData = { ...envData, ...cliForEnv }
    }
    try {
      // 单次写入 / Single write
      await executor.writeEnvFile(selectedSuffix.value, envData)
    } catch (e: unknown) {
      const err = e as Error
      message.error(t('executor.envSaveFailed', { reason: err?.message || String(e) }))
      return
    }
  } else {
    // Converter 模式：保存转换参数到 store / Converter mode: save converter params to store
    converter.setEditorConverterParams(props.filePath || '__default__', {
      direction: converterDirection.value,
      outputPath: converterOutputPath.value,
    })
  }

  message.success(t('editor.paramEdit.saved'))
  emit('update:visible', false)
}

function handleCancel() {
  emit('update:visible', false)
}

const title = computed(() =>
  isExecutor.value ? t('editor.toolbar.editRunParams') : t('editor.toolbar.editConvertParams'),
)

</script>

<template>
  <a-modal
    :open="visible"
    :title="title"
    width="520px"
    @ok="handleSave"
    @cancel="handleCancel"
    :ok-text="t('editor.paramEdit.confirm')"
    :cancel-text="t('dialog.cancel')"
  >
    <a-spin :spinning="!loaded">
      <div class="param-form">
        <!-- Executor mode -->
        <template v-if="isExecutor">
          <!-- 运行环境选择 / Env suffix selection -->
          <div class="param-section">
            <span class="section-title">{{ t('executor.form_envSuffix') }}</span>
            <a-select v-model:value="selectedSuffix" style="width: 200px">
              <a-select-option v-for="s in envSuffixes" :key="s" :value="s">
                {{ s || 'env.yml (default)' }}
              </a-select-option>
            </a-select>
          </div>

          <!-- Env-only 参数（YAML 编辑）/ Env-only params (YAML editing) -->
          <div class="param-section">
            <div class="block-header">
              <span class="section-title">{{ t('executor.form_block1Title') }}</span>
              <a-tag color="red">{{ t('executor.form_envOnly') }}</a-tag>
            </div>
            <p class="hint">{{ t('executor.form_block1Desc') }}</p>
            <div class="env-yaml-edit-area">
              <a-textarea
                v-model:value="envYamlText"
                :rows="8"
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
          </div>

          <!-- CLI 参数 / CLI params -->
          <div class="param-section">
            <span class="section-title">{{ t('executor.form_block2Title') }}</span>

            <div class="param-row">
              <label>{{ t('executor.param_scriptType') }}</label>
              <a-input v-model:value="cliParams.scriptType" size="small" />
            </div>
            <div class="param-row">
              <label>{{ t('executor.param_maxThread') }}</label>
              <a-input-number v-model:value="cliParams.maxThread" :min="1" :max="50" size="small" style="width: 100%" />
            </div>
            <div class="param-row">
              <label>{{ t('executor.param_reportName') }}</label>
              <a-input v-model:value="cliParams.reportName" size="small" />
            </div>
            <div class="param-row">
              <label>{{ t('executor.param_apiMode') }}</label>
              <a-select v-model:value="cliParams.apiMode" size="small" style="width: 120px">
                <a-select-option value="all">all</a-select-option>
                <a-select-option value="single">single</a-select-option>
                <a-select-option value="biz">biz</a-select-option>
              </a-select>
            </div>
          </div>

          <!-- JsonEditor 弹窗（可视化编辑 env-only）/ JsonEditor modal (visual editing for env-only) -->
          <JsonEditor
            :visible="showFullEnvEditor"
            :value="envOnlyParamsForDisplay"
            :title="t('executor.form_block1Title')"
            @confirm="onEnvEditorConfirm"
            @cancel="showFullEnvEditor = false"
          />
        </template>

        <!-- Converter mode / 转换器模式 -->
        <template v-else>
          <!-- 转换方向 / Direction -->
          <div class="param-section">
            <span class="section-title">{{ t('editor.paramEdit.converterDirection') }}</span>
            <a-select
              v-model:value="converterDirection"
              style="width: 240px"
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

          <!-- 输入 / Input -->
          <div class="param-section">
            <span class="section-title">{{ t('converter.form_input') }}</span>
            <div class="param-row">
              <label>{{ t('editor.paramEdit.converterInputFile') }}</label>
              <a-input :value="converterInputPath" size="small" disabled />
            </div>
          </div>

          <!-- 输出 / Output -->
          <div class="param-section">
            <span class="section-title">{{ t('converter.form_output') }}</span>
            <div class="param-row">
              <label>{{ t('converter.param_output') }}</label>
              <a-input-group compact>
                <a-input v-model:value="converterOutputPath" size="small" style="width: calc(100% - 80px)" />
                <a-button v-if="isConverterYamlOutput" size="small" @click="browseConverterOutputDir">{{ t('agent.settings_browse') }}</a-button>
                <a-button v-else size="small" @click="browseConverterOutputFile">{{ t('agent.settings_browse') }}</a-button>
              </a-input-group>
            </div>
          </div>
        </template>
      </div>
    </a-spin>
  </a-modal>
</template>

<style scoped>
.param-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.param-section {
  padding-bottom: 12px;
  border-bottom: 1px solid #f0f0f0;
}
.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #333;
}
.hint {
  color: #999;
  font-size: 12px;
  margin: 4px 0 8px 0;
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
  margin-bottom: 4px;
}
</style>
