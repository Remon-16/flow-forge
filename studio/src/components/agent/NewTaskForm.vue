<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { useAgentStore } from '../../stores/agent'
import { openDirectoryDialog, openFileDialog, readFile, isDesktop } from '../../utils/desktop-bridge'
import ConfigPanel from './ConfigPanel.vue'

const { t } = useI18n()
const agent = useAgentStore()

const emit = defineEmits<{
  submit: [params: { cliArgs: string[] }]
}>()

// 基础输入 / Basic inputs
const outputDir = ref('')
const requirementPath = ref('')
const apiPath = ref('')
const autoMode = ref(false)
const userGuidance = ref('')
const caseType = ref<'single' | 'biz' | 'both'>('both')

// LLM 配置（从 YAML 读取）/ LLM config (read from YAML)
const llmConfig = ref<Record<string, any>>({})
const configLoaded = ref(false)
const configError = ref('')
const loadingConfig = ref(false)

// 其他配置覆盖值 / Other config overrides
const configOverrides = ref<Record<string, any>>({})

// 浏览目录 / Browse directory
async function browseDir(target: 'output') {
  try {
    const dir = await openDirectoryDialog()
    if (dir && target === 'output') outputDir.value = dir
  } catch { /* cancelled */ }
}

// 浏览文件 / Browse file
async function browseFile(target: 'requirement' | 'api') {
  try {
    const file = await openFileDialog()
    if (file) {
      if (target === 'requirement') requirementPath.value = file
      else apiPath.value = file
    }
  } catch { /* cancelled */ }
}

// 加载配置文件 / Load config file
async function loadYamlConfig() {
  if (!agent.config.agentRootDir) {
    configError.value = 'Agent root directory not configured'
    return
  }
  loadingConfig.value = true
  configError.value = ''
  try {
    const configPath = `${agent.config.agentRootDir}/${agent.config.configFileName}`
    const content = await readFile(configPath)
    // 简单 YAML 解析（仅读取 llm 节）/ Simple YAML parse (read llm section only)
    // 对简单嵌套结构的 YAML 进行正则解析 / Regex-based parsing for simple YAML
    const llm: Record<string, any> = {}
    let inLlm = false
    for (const line of content.split('\n')) {
      if (/^llm\s*:/.test(line.trim())) {
        inLlm = true
        continue
      }
      if (inLlm && /^\w/.test(line.trim()) && !line.trim().startsWith('#')) {
        break // 回到顶层 / Back to top level
      }
      if (inLlm) {
        const m = line.match(/^\s+(\w[\w_]*)\s*:\s*(.+)\s*$/)
        if (m) {
          const key = m[1]
          let val = m[2].trim()
          // 移除引号 / Remove quotes
          if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'"))) {
            val = val.slice(1, -1)
          }
          // 尝试解析为数字 / Try parse as number
          const num = Number(val)
          llm[key] = isNaN(num) ? val : num
        }
      }
    }
    llmConfig.value = llm
    configLoaded.value = true
  } catch (e: any) {
    configError.value = e?.message || String(e)
  } finally {
    loadingConfig.value = false
  }
}

// 保存 LLM 配置到 YAML / Save LLM config to YAML
async function saveLlmConfig() {
  if (!agent.config.agentRootDir) return
  try {
    const { writeFile } = await import('../../utils/desktop-bridge')
    const configPath = `${agent.config.agentRootDir}/${agent.config.configFileName}`
    const content = await readFile(configPath)
    // 替换 llm 节 / Replace llm section
    const lines = content.split('\n')
    let inLlm = false
    const resultLines: string[] = []
    const written = new Set<string>()
    for (const line of lines) {
      if (/^llm\s*:/.test(line.trim())) {
        inLlm = true
        resultLines.push('llm:')
        for (const [key, val] of Object.entries(llmConfig.value)) {
          const yamlVal = typeof val === 'string' ? `"${val}"` : String(val)
          resultLines.push(`  ${key}: ${yamlVal}`)
          written.add(key)
        }
        continue
      }
      if (inLlm && /^\w/.test(line.trim()) && !line.trim().startsWith('#')) {
        inLlm = false
      }
      if (inLlm) continue // 跳过旧的 llm 行 / Skip old llm lines
      resultLines.push(line)
    }
    await writeFile(configPath, resultLines.join('\n'))
    message.success(t('agent.form_llmSaved'))
  } catch (e: any) {
    message.error(e?.message || 'Save failed')
  }
}

// 处理配置覆盖 / Handle config override
function handleConfigChange(path: string, value: any) {
  configOverrides.value[path] = value
}

// 提交 / Submit
async function handleSubmit() {
  if (!outputDir.value) {
    message.warning('Output directory is required')
    return
  }

  const taskId = await agent.createTask({
    outputDir: outputDir.value,
    requirementPath: requirementPath.value,
    apiPath: apiPath.value,
    autoMode: autoMode.value,
    userGuidance: userGuidance.value,
    caseType: caseType.value,
  })

  // 构建 CLI 覆盖参数 / Build CLI override args
  const cliArgs: string[] = []
  for (const [path, val] of Object.entries(configOverrides.value)) {
    if (val === undefined || val === null || val === '') continue
    // 将 pipeline.max_steps 转为 --max-steps
    const parts = path.split('.')
    const section = parts[0]
    const key = parts[1]

    if (section === 'pipeline') {
      if (key === 'auto') { if (val) cliArgs.push('--auto'); continue }
      if (key === 'case_type') { cliArgs.push('--case-type', String(val)); continue }
      cliArgs.push(`--${key.replace(/_/g, '-')}`, String(val))
    } else if (section === 'validation' && key === 'enabled') {
      cliArgs.push(val ? '--validation' : '--no-validation')
    } else if (section === 'knowledge') {
      cliArgs.push(val ? '--knowledge' : '--no-knowledge')
    } else if (section === 'plugins') {
      cliArgs.push(val ? '--plugins' : '--no-plugins')
    } else if (section === 'skills') {
      cliArgs.push(val ? '--skills' : '--no-skills')
    } else if (section === 'logging' && key === 'log_to_output' && val) {
      cliArgs.push('--log-to-output')
    }
  }

  await agent.startTask(taskId, cliArgs)
}

// 桌面检测 / Desktop detection
const isDesktopMode = isDesktop

// 自动加载配置 / Auto-load config if agent root is set
if (agent.config.agentRootDir && !configLoaded.value && !configError.value) {
  loadYamlConfig()
}
</script>

<template>
  <div class="new-task-form">
    <!-- 基础输入 / Basic inputs -->
    <div class="form-section">
      <h4>Basic Settings</h4>

      <div class="form-row">
        <label>{{ t('agent.form_outputDir') }} *</label>
        <a-input-group compact>
          <a-input v-model:value="outputDir" style="width: calc(100% - 80px)" placeholder="./output" />
          <a-button @click="browseDir('output')">{{ t('agent.settings_browse') }}</a-button>
        </a-input-group>
      </div>

      <div class="form-row">
        <label>{{ t('agent.form_requirement') }}</label>
        <a-input-group compact>
          <a-input v-model:value="requirementPath" style="width: calc(100% - 80px)" placeholder="docs/req.md" />
          <a-button @click="browseFile('requirement')">{{ t('agent.settings_browse') }}</a-button>
        </a-input-group>
      </div>

      <div class="form-row">
        <label>{{ t('agent.form_api') }}</label>
        <a-input-group compact>
          <a-input v-model:value="apiPath" style="width: calc(100% - 80px)" placeholder="docs/api.yaml" />
          <a-button @click="browseFile('api')">{{ t('agent.settings_browse') }}</a-button>
        </a-input-group>
      </div>

      <div class="form-row inline">
        <label>{{ t('agent.form_autoMode') }}</label>
        <a-switch v-model:checked="autoMode" size="small" />
      </div>

      <div class="form-row">
        <label>{{ t('agent.form_userGuidance') }}</label>
        <a-textarea v-model:value="userGuidance" :rows="3" placeholder="Optional user guidance..." />
      </div>
    </div>

    <!-- LLM 配置 / LLM Config -->
    <div class="form-section">
      <h4>{{ t('agent.form_llmConfig') }}</h4>

      <a-button
        v-if="!configLoaded && !configError"
        size="small"
        :loading="loadingConfig"
        @click="loadYamlConfig"
      >
        Load from {{ agent.config.configFileName }}
      </a-button>

      <a-alert v-if="configError" type="warning" :message="configError" show-icon style="margin-bottom: 8px;" />

      <div v-if="configLoaded" class="llm-fields">
        <div v-for="(val, key) in llmConfig" :key="key" class="form-row">
          <label>{{ key }}</label>
          <template v-if="typeof val === 'boolean'">
            <a-switch v-model:checked="llmConfig[key]" size="small" />
          </template>
          <template v-else-if="key === 'api_key'">
            <a-input-password v-model:value="llmConfig[key]" size="small" />
          </template>
          <template v-else>
            <a-input v-model:value="llmConfig[key]" size="small" />
          </template>
        </div>
        <a-button size="small" type="primary" @click="saveLlmConfig" style="margin-top: 8px;">
          {{ t('agent.form_llmSave') }}
        </a-button>
      </div>
    </div>

    <!-- 其他配置 / Other config -->
    <div class="form-section">
      <h4>{{ t('agent.form_otherConfig') }}</h4>
      <ConfigPanel :config-data="{}" @change="handleConfigChange" />
    </div>

    <!-- 提交 / Submit -->
    <div class="form-actions">
      <a-button type="primary" size="large" @click="handleSubmit">
        {{ t('agent.form_submit') }}
      </a-button>
    </div>
  </div>
</template>

<style scoped>
.new-task-form {
  padding: 16px 24px;
  overflow-y: auto;
  height: 100%;
}
.form-section {
  margin-bottom: 24px;
}
.form-section h4 {
  font-size: 14px;
  font-weight: 600;
  color: #333;
  margin: 0 0 12px 0;
  padding-bottom: 8px;
  border-bottom: 1px solid #f0f0f0;
}
.form-row {
  margin-bottom: 12px;
}
.form-row.inline {
  display: flex;
  align-items: center;
  gap: 12px;
}
.form-row label {
  display: block;
  font-size: 13px;
  color: #555;
  margin-bottom: 4px;
}
.form-row.inline label {
  margin-bottom: 0;
}
.llm-fields {
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  padding: 12px;
  background: #fafafa;
}
.form-actions {
  display: flex;
  justify-content: flex-end;
  padding: 16px 0;
  border-top: 1px solid #f0f0f0;
  position: sticky;
  bottom: 0;
  background: #fff;
}
</style>
