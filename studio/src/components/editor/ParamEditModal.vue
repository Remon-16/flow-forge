<script setup lang="ts">
// ParamEditModal — 参数编辑模态框（从编辑器工具栏触发）。
// Parameter edit modal for editor toolbar — edit run/convert params.
import { ref, watch, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useExecutorStore } from '../../stores/executor'
import { useAgentStore } from '../../stores/agent'
import { DEFAULT_CLI_PARAMS, type ExecutorCliParams } from '../../types/executor'
import { message } from 'ant-design-vue'

const { t } = useI18n()
const executor = useExecutorStore()
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

// Env-only params (for executor mode only)
const envOnlyParams = ref<Record<string, unknown>>({})
const selectedSuffix = ref('')

// 新增参数状态 / Add parameter state
const addingParam = ref(false)
const newKeyName = ref('')
const addingSubKey = ref<Record<string, boolean>>({})
const newSubKeyName = ref<Record<string, string>>({})

watch(() => props.visible, async (v) => {
  if (!v) return

  // 从 store 加载上次保存的参数 / Load last saved params from store
  const saved = executor.getEditorCliParams(props.filePath || '__default__')
  cliParams.value = { ...saved }

  // 如果是 executor 模式，加载 env 数据 / Load env data for executor mode
  if (isExecutor.value) {
    const suffixes = await executor.readEnvSuffixes()
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
    }
  }

  loaded.value = true
})

/**
 * 保存参数到 store 并写入 env 文件。
 * Save params to store and write to env file.
 * 异步等待写入完成后再关闭模态框，失败时弹错误提示。
 * Awaits write completion before closing; shows error on failure.
 */
async function handleSave() {
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

// 用于去除 _app_ 前缀的显示标签 / Display label with _app_ prefix stripped
function displayLabel(key: string): string {
  return key.startsWith('_app_') ? key.slice(5) : key
}

// ---- 新增/删除 env 参数 / Add/Delete env params ----

function addEnvParam() {
  const name = newKeyName.value.trim()
  if (!name) return
  envOnlyParams.value[name] = ''
  newKeyName.value = ''
  addingParam.value = false
}

function deleteEnvParam(key: string) {
  const updated: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(envOnlyParams.value)) {
    if (k !== key) updated[k] = v
  }
  envOnlyParams.value = updated
}

function addSubParam(parentKey: string) {
  const name = (newSubKeyName.value[parentKey] || '').trim()
  if (!name) return
  const parent = envOnlyParams.value[parentKey] as Record<string, unknown>
  if (parent && typeof parent === 'object') {
    parent[name] = ''
  }
  newSubKeyName.value[parentKey] = ''
  addingSubKey.value[parentKey] = false
}

function deleteSubParam(parentKey: string, subKey: string) {
  const parent = envOnlyParams.value[parentKey] as Record<string, unknown>
  if (parent && typeof parent === 'object') {
    delete parent[subKey]
  }
}
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
        <!-- Executor CLI params -->
        <template v-if="isExecutor">
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

          <!-- Env-only params / 仅 env 参数 -->
          <div class="param-section env-section">
            <span class="section-title">{{ t('executor.form_block1Title') }}</span>
            <p class="hint">{{ t('executor.form_block1Desc') }}</p>
            <template v-for="(val, key) in envOnlyParams" :key="String(key)">
              <!-- 标量/字符串值：可编辑输入框 + 删除 / Scalar/string: editable input + delete -->
              <div v-if="typeof val === 'string' || typeof val === 'number'" class="param-row">
                <div class="param-row-header">
                  <label>{{ displayLabel(key) }}</label>
                  <a-button type="text" size="small" danger @click="deleteEnvParam(String(key))">✕</a-button>
                </div>
                <a-input
                  :value="String(val)"
                  size="small"
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
                      <span v-else class="param-value-readonly">{{ typeof sub2Val === 'object' ? JSON.stringify(sub2Val) : String(sub2Val) }}</span>
                    </div>
                  </div>
                  <a-switch
                    v-else-if="typeof subVal === 'boolean'"
                    :checked="subVal"
                    size="small"
                    @change="(v: boolean) => {
                      const obj = envOnlyParams[key] as Record<string, unknown>
                      obj[subKey] = v
                    }"
                  />
                  <span v-else class="param-value-readonly">{{ Array.isArray(subVal) ? JSON.stringify(subVal) : String(subVal) }}</span>
                </div>
                <!-- 嵌套组内新增子属性 / Add sub-property inside nested group -->
                <a-button v-if="!addingSubKey[key]" type="dashed" size="small" style="margin-top: 4px" @click="addingSubKey[key] = true">
                  + {{ t('executor.form_addParam') }}
                </a-button>
                <a-input-group v-else compact style="margin-top: 4px">
                  <a-input size="small" v-model:value="newSubKeyName[key]" :placeholder="t('executor.form_newParamHint')" style="width: 60%" />
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
              <!-- 数组/其他：只读文本 + 删除 / Array/other: readonly text + delete -->
              <div v-else class="param-row">
                <div class="param-row-header">
                  <label>{{ displayLabel(key) }}</label>
                  <a-button type="text" size="small" danger @click="deleteEnvParam(String(key))">✕</a-button>
                </div>
                <span class="param-value-readonly">{{ Array.isArray(val) ? JSON.stringify(val) : String(val) }}</span>
              </div>
            </template>

            <!-- 新增 env 参数 / Add env param -->
            <div style="margin-top: 8px; display: flex; gap: 8px;">
              <a-button v-if="!addingParam" type="dashed" size="small" @click="addingParam = true">
                + {{ t('executor.form_addParam') }}
              </a-button>
              <template v-else>
                <a-input size="small" v-model:value="newKeyName" :placeholder="t('executor.form_newParamHint')" style="width: 160px" />
                <a-button size="small" type="primary" @click="addEnvParam">{{ t('dialog.confirm') }}</a-button>
                <a-button size="small" @click="addingParam = false">{{ t('dialog.cancel') }}</a-button>
              </template>
            </div>
          </div>
        </template>

        <!-- Converter params (placeholder) -->
        <template v-else>
          <p class="hint">{{ t('editor.paramEdit.converterHint') }}</p>
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
.env-section {
  max-height: 300px;
  overflow-y: auto;
}
/* 嵌套对象组 / Nested object group */
.param-group {
  margin-top: 4px;
  padding: 6px 8px;
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  background: #fafafa;
}
.group-label {
  font-size: 12px;
  font-weight: 600;
  color: #555;
  display: block;
  margin-bottom: 4px;
}
.group-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
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
</style>
