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
      envOnlyParams.value = await executor.readEnvFile(selectedSuffix.value)
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

  // Executor mode: 写 env-only 参数到 env 文件 / Write env-only params to env
  if (isExecutor.value && selectedSuffix.value) {
    try {
      await executor.writeEnvFile(selectedSuffix.value, envOnlyParams.value)
    } catch (e: unknown) {
      const err = e as Error
      message.error(t('executor.envSaveFailed', { reason: err?.message || String(e) }))
      return
    }
  }

  // 如果同步开关打开，写 CLI 参数到 env / If sync toggle on, write CLI params to env
  if (agent.config.saveToEnvFile && isExecutor.value && selectedSuffix.value) {
    const cliForEnv: Record<string, unknown> = {
      scriptType: cliParams.value.scriptType,
      envName: cliParams.value.envName,
      maxThread: cliParams.value.maxThread,
      reportName: cliParams.value.reportName,
      apiMode: cliParams.value.apiMode,
    }
    try {
      await executor.writeEnvFile(selectedSuffix.value, { ...envOnlyParams.value, ...cliForEnv })
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

          <!-- Env-only params (read-only view) -->
          <div class="param-section env-section">
            <span class="section-title">{{ t('executor.form_block1Title') }}</span>
            <p class="hint">{{ t('executor.form_block1Desc') }}</p>
            <div class="param-row" v-for="(val, key) in envOnlyParams" :key="String(key)">
              <label>{{ key }}</label>
              <a-input
                v-if="typeof val === 'string' || typeof val === 'number'"
                :value="String(val)"
                size="small"
                @change="e => {
                  const target = e.target as HTMLInputElement
                  envOnlyParams[key] = target.value
                }"
              />
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
  max-height: 200px;
  overflow-y: auto;
}
</style>
