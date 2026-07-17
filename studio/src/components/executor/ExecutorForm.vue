<script setup lang="ts">
// ExecutorForm — 执行前配置表单。
// Pre-execution config form: env suffix selection, Block1 (env-only) + Block2 (CLI params).
import { ref, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useExecutorStore } from '../../stores/executor'
import { useAgentStore } from '../../stores/agent'
import { DEFAULT_CLI_PARAMS } from '../../types/executor'
import type { ExecutorCliParams } from '../../types/executor'
import { openFileDialog, openDirectoryDialog } from '../../utils/desktop-bridge'
import { normalizeJsonValue } from '../../utils/json-helper'
import JsonEditor from '../json-editor/JsonEditor.vue'
import { message } from 'ant-design-vue'

const { t } = useI18n()
const executor = useExecutorStore()
const agent = useAgentStore()

// 用于去除 _app_ 前缀的显示标签 / Display label with _app_ prefix stripped
function displayLabel(key: string): string {
  return key.startsWith('_app_') ? key.slice(5) : key
}

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

// 新增参数状态 / Add parameter state
const addingParam = ref(false)
const newKeyName = ref('')
// 新增参数类型选择 / New parameter type selection
const newKeyType = ref<string>('string')
const TYPE_OPTIONS = [
  { value: 'string', label: 'String' },
  { value: 'number', label: 'Number' },
  { value: 'boolean', label: 'Boolean' },
  { value: 'Dict', label: 'Dict { }' },
  { value: 'List', label: 'List [ ]' },
]
// 嵌套组内新增子属性状态 / Add sub-property inside nested group state
const addingSubKey = ref<Record<string, boolean>>({})
const newSubKeyName = ref<Record<string, string>>({})
const newSubKeyType = ref<Record<string, string>>({})

// JSON 编辑器模态框状态 / JSON editor modal state
const showEnvJsonEditor = ref(false)
const editingJsonKey = ref('')
const editingJsonValue = ref<Record<string, unknown>>({})

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
    await executor.writeEnvFile(selectedSuffix.value, envOnlyParams.value)
    message.success(t('executor.envSaved'))
  } catch (e: unknown) {
    const err = e as Error
    message.error(t('executor.envSaveFailed', { reason: err?.message || String(e) }))
  }
}

// ---- Add / Delete env params / 新增/删除 env 参数 ----

/** 新增顶层 env 参数（支持类型选择）/ Add top-level env param (with type selection) */
function addEnvParam() {
  const name = newKeyName.value.trim()
  if (!name) return
  switch (newKeyType.value) {
    case 'number':
      envOnlyParams.value[name] = 0
      break
    case 'boolean':
      envOnlyParams.value[name] = false
      break
    case 'Dict':
      envOnlyParams.value[name] = {}
      break
    case 'List':
      envOnlyParams.value[name] = []
      break
    default:
      envOnlyParams.value[name] = ''
  }
  newKeyName.value = ''
  newKeyType.value = 'string'
  addingParam.value = false
}

/** 删除顶层 env 参数 / Delete top-level env param */
function deleteEnvParam(key: string) {
  const updated: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(envOnlyParams.value)) {
    if (k !== key) updated[k] = v
  }
  envOnlyParams.value = updated
}

/** 在嵌套对象内新增子属性（支持类型选择）/ Add sub-property inside nested object (with type selection) */
function addSubParam(parentKey: string) {
  const name = (newSubKeyName.value[parentKey] || '').trim()
  if (!name) return
  const parent = envOnlyParams.value[parentKey] as Record<string, unknown>
  if (parent && typeof parent === 'object' && !Array.isArray(parent)) {
    const type = newSubKeyType.value[parentKey] || 'string'
    switch (type) {
      case 'number':
        parent[name] = 0
        break
      case 'boolean':
        parent[name] = false
        break
      case 'Dict':
        parent[name] = {}
        break
      case 'List':
        parent[name] = []
        break
      default:
        parent[name] = ''
    }
  }
  newSubKeyName.value[parentKey] = ''
  newSubKeyType.value[parentKey] = 'string'
  addingSubKey.value[parentKey] = false
}

/** 删除嵌套对象内的子属性 / Delete sub-property inside nested object */
function deleteSubParam(parentKey: string, subKey: string) {
  const parent = envOnlyParams.value[parentKey] as Record<string, unknown>
  if (parent && typeof parent === 'object') {
    delete parent[subKey]
  }
}

// ---- JSON 编辑器集成 / JSON editor integration ----

/**
 * 打开 JSON 编辑器编辑只读复杂值（数组/深层对象）。
 * Open JSON editor to edit readonly complex values (arrays/deep objects).
 * 数组值包裹为 { items: val } 对象（JsonEditor 期望 Record 类型）。
 * Arrays wrapped as { items: val } (JsonEditor expects Record).
 */
function openEnvJsonEditor(key: string, val: unknown) {
  editingJsonKey.value = key
  if (Array.isArray(val)) {
    editingJsonValue.value = { items: val }
  } else {
    editingJsonValue.value = normalizeJsonValue(val)
  }
  showEnvJsonEditor.value = true
}

/**
 * JSON 编辑器确认回调：还原包裹的数组并更新 env 参数。
 * JSON editor confirm: unwrap arrays and update env params.
 */
function onEnvJsonConfirm(value: Record<string, unknown>) {
  if (editingJsonKey.value) {
    const keys = Object.keys(value)
    // 还原包裹的数组 / Unwrap the array
    if (keys.length === 1 && keys[0] === 'items' && Array.isArray(value.items)) {
      envOnlyParams.value[editingJsonKey.value] = value.items
    } else {
      envOnlyParams.value[editingJsonKey.value] = value
    }
  }
  showEnvJsonEditor.value = false
}

// ---- Submit / 提交 ----

async function handleSubmit() {
  if (!agent.config.executorRootDir) {
    message.warning(t('executor.noExecutorRoot'))
    return
  }

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

        <div class="param-list">
          <template v-for="(val, key) in envOnlyParams" :key="key">
            <!-- 标量/字符串值：可编辑输入框 + 删除按钮 / Scalar/string: editable input + delete -->
            <div v-if="typeof val === 'string' || typeof val === 'number'" class="param-row">
              <div class="param-row-header">
                <label>{{ displayLabel(key) }}</label>
                <a-button type="text" size="small" danger @click="deleteEnvParam(String(key))">✕</a-button>
              </div>
              <a-input
                :value="String(val)"
                @change="e => {
                  const target = e.target as HTMLInputElement
                  envOnlyParams[key] = target.value
                }"
              />
            </div>
            <!-- 嵌套对象：展开子属性（支持二级嵌套）/ Nested object: expand sub-properties (depth-2) -->
            <div v-else-if="typeof val === 'object' && val !== null && !Array.isArray(val)" class="param-group">
              <div class="group-header">
                <span class="group-label">{{ displayLabel(key) }}</span>
                <a-button type="text" size="small" danger @click="deleteEnvParam(String(key))">✕</a-button>
              </div>
              <div v-for="(subVal, subKey) in val as Record<string, unknown>" :key="subKey" class="param-row indent-row">
                <div class="param-row-header">
                  <label>{{ subKey }}</label>
                  <a-button type="text" size="small" danger @click="deleteSubParam(String(key), String(subKey))">✕</a-button>
                </div>
                <!-- 标量子值 / Scalar sub-value -->
                <a-input
                  v-if="typeof subVal === 'string' || typeof subVal === 'number'"
                  :value="String(subVal)"
                  size="small"
                  @change="e => {
                    const target = e.target as HTMLInputElement
                    const obj = envOnlyParams[key] as Record<string, unknown>
                    obj[subKey] = target.value
                  }"
                />
                <!-- 二级嵌套对象 / Second-level nested object -->
                <div v-else-if="typeof subVal === 'object' && subVal !== null && !Array.isArray(subVal)" class="param-group indent-group">
                  <span class="group-label">{{ subKey }}</span>
                  <div v-for="(sub2Val, sub2Key) in subVal as Record<string, unknown>" :key="sub2Key" class="param-row indent-row">
                    <label>{{ sub2Key }}</label>
                    <a-input
                      v-if="typeof sub2Val === 'string' || typeof sub2Val === 'number'"
                      :value="String(sub2Val)"
                      size="small"
                      @change="e => {
                        const target = e.target as HTMLInputElement
                        const obj2 = (envOnlyParams[key] as Record<string, unknown>)[subKey] as Record<string, unknown>
                        obj2[sub2Key] = target.value
                      }"
                    />
                    <div v-else style="display: flex; align-items: center; gap: 4px;">
                      <span class="param-value-readonly" style="flex: 1;">{{ typeof sub2Val === 'object' ? JSON.stringify(sub2Val) : String(sub2Val) }}</span>
                      <a-button size="small" type="link" @click="openEnvJsonEditor(String(key) + '.' + String(subKey) + '.' + String(sub2Key), sub2Val)">
                        {{ t('jsonEditor.editDetails') }}
                      </a-button>
                    </div>
                  </div>
                </div>
                <!-- 布尔子值 / Boolean sub-value -->
                <a-switch
                  v-else-if="typeof subVal === 'boolean'"
                  :checked="subVal"
                  size="small"
                  @change="(v: boolean) => {
                    const obj = envOnlyParams[key] as Record<string, unknown>
                    obj[subKey] = v
                  }"
                />
                <!-- 数组/其他：只读文本 + 编辑 / Array/other: readonly text + edit -->
                <div v-else style="display: flex; align-items: center; gap: 4px;">
                  <span class="param-value-readonly" style="flex: 1;">{{ Array.isArray(subVal) ? JSON.stringify(subVal) : String(subVal) }}</span>
                  <a-button size="small" type="link" @click="openEnvJsonEditor(String(key) + '.' + String(subKey), subVal)">
                    {{ t('jsonEditor.editDetails') }}
                  </a-button>
                </div>
              </div>
              <!-- 在嵌套组内新增子属性 / Add sub-property inside nested group -->
              <a-button v-if="!addingSubKey[key]" type="dashed" size="small" style="margin-top: 4px" @click="addingSubKey[key] = true; newSubKeyType[key] = 'string'">
                + {{ t('executor.form_addParam') }}
              </a-button>
              <a-input-group v-else compact style="margin-top: 4px">
                <a-input size="small" v-model:value="newSubKeyName[key]" :placeholder="t('executor.form_newParamHint')" style="width: 40%" />
                <a-select v-model:value="newSubKeyType[key]" size="small" style="width: 30%">
                  <a-select-option v-for="opt in TYPE_OPTIONS" :key="opt.value" :value="opt.value">
                    {{ opt.label }}
                  </a-select-option>
                </a-select>
                <a-button size="small" type="primary" @click="addSubParam(String(key))">{{ t('dialog.confirm') }}</a-button>
                <a-button size="small" @click="addingSubKey[key] = false">{{ t('dialog.cancel') }}</a-button>
              </a-input-group>
            </div>
            <!-- 布尔值 / Boolean -->
            <div v-else-if="typeof val === 'boolean'" class="param-row">
              <div class="param-row-header">
                <label>{{ displayLabel(key) }}</label>
                <a-button type="text" size="small" danger @click="deleteEnvParam(String(key))">✕</a-button>
              </div>
              <a-switch
                :checked="val"
                size="small"
                @change="(v: boolean) => { envOnlyParams[key] = v }"
              />
            </div>
            <!-- 数组/其他：只读文本 + 编辑 + 删除 / Array/other: readonly text + edit + delete -->
            <div v-else class="param-row">
              <div class="param-row-header">
                <label>{{ displayLabel(key) }}</label>
                <div style="display: flex; gap: 4px;">
                  <a-button size="small" type="link" @click="openEnvJsonEditor(String(key), envOnlyParams[key])">
                    {{ t('jsonEditor.editDetails') }}
                  </a-button>
                  <a-button type="text" size="small" danger @click="deleteEnvParam(String(key))">✕</a-button>
                </div>
              </div>
              <span class="param-value-readonly">{{ Array.isArray(val) ? JSON.stringify(val) : String(val) }}</span>
            </div>
          </template>
        </div>

        <!-- 新增 env 参数 / Add env param -->
        <div style="margin-top: 8px; display: flex; gap: 8px;">
          <a-button v-if="!addingParam" type="dashed" size="small" @click="addingParam = true">
            + {{ t('executor.form_addParam') }}
          </a-button>
          <template v-else>
            <a-input size="small" v-model:value="newKeyName" :placeholder="t('executor.form_newParamHint')" style="width: 140px" />
            <a-select v-model:value="newKeyType" size="small" style="width: 100px">
              <a-select-option v-for="opt in TYPE_OPTIONS" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </a-select-option>
            </a-select>
            <a-button size="small" type="primary" @click="addEnvParam">{{ t('dialog.confirm') }}</a-button>
            <a-button size="small" @click="addingParam = false">{{ t('dialog.cancel') }}</a-button>
          </template>
        </div>

        <a-button size="small" @click="handleSaveEnv" style="margin-top: 8px">
          {{ t('executor.form_saveEnv') }}
        </a-button>
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

    <!-- JsonEditor 模态框（复杂值编辑）/ JsonEditor modal (complex value editing) -->
    <JsonEditor
      :visible="showEnvJsonEditor"
      :value="editingJsonValue"
      :title="editingJsonKey"
      @confirm="onEnvJsonConfirm"
      @cancel="showEnvJsonEditor = false"
    />

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
