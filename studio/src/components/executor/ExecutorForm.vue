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
import { message } from 'ant-design-vue'

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

async function loadEnvData() {
  const data = await executor.readEnvFile(selectedSuffix.value)
  // 分离 Block1 (env-only) 和 Block2 (CLI available) 参数
  // Separate Block1 (env-only) and Block2 (CLI available) params
  const cliKeys = ['scriptType', 'envName', 'maxThread', 'reportName', 'apiMode', 'caseFilePath']
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
    envName: (block2.envName as string) || selectedSuffix.value || DEFAULT_CLI_PARAMS.envName,
    maxThread: Number(block2.maxThread) || DEFAULT_CLI_PARAMS.maxThread,
    reportName: (block2.reportName as string) || DEFAULT_CLI_PARAMS.reportName,
    apiMode: (block2.apiMode as string) || DEFAULT_CLI_PARAMS.apiMode,
  }

  const cfp = data['caseFilePath']
  if (cfp && typeof cfp === 'string') caseFilePath.value = cfp
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
  } catch {
    message.error(t('executor.envSaveFailed'))
  }
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
      envName: cliParams.value.envName,
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
          <div v-for="(val, key) in envOnlyParams" :key="key" class="param-row">
            <label>{{ key }}</label>
            <a-input
              v-if="typeof val === 'string' || typeof val === 'number'"
              :value="String(val)"
              @change="e => {
                const target = e.target as HTMLInputElement
                envOnlyParams[key] = target.value
              }"
            />
          </div>
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
              <a-select-option value="all">all</a-select-option>
              <a-select-option value="single">single</a-select-option>
              <a-select-option value="biz">biz</a-select-option>
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
.form-footer {
  margin-top: auto;
  padding-top: 16px;
}
</style>
