<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { useAgentStore } from '../../stores/agent'
import { openDirectoryDialog, openFileDialog, readFile, isDesktop } from '../../utils/desktop-bridge'
import yaml from 'js-yaml'
import YAML from 'yaml'
import ConfigPanel from './ConfigPanel.vue'
import JsonEditor from '../json-editor/JsonEditor.vue'

const { t } = useI18n()
const agent = useAgentStore()

const emit = defineEmits<{
  submit: [params: { cliArgs: string[] }]
}>()

// 基础输入 / Basic inputs
const outputDir = ref('')
const requirementPaths = ref('')
const apiPaths = ref('')
const autoMode = ref(false)
const userGuidance = ref('')
const caseType = ref<'single' | 'biz' | 'both'>('both')

// LLM 配置（从 YAML 读取）/ LLM config (read from YAML)
const llmConfig = ref<Record<string, any>>({})
// 完整配置（pipeline/validation/plugins/skills/logging）供 ConfigPanel 使用 / Full config for ConfigPanel
const fullConfig = ref<Record<string, any>>({})
const configLoaded = ref(false)
const configError = ref('')
const loadingConfig = ref(false)

// 其他配置覆盖值 / Other config overrides
const configOverrides = ref<Record<string, any>>({})

// extra_params 结构化编辑（使用 JsonEditor 模态框）/ extra_params structured editing (uses JsonEditor modal)
const extraParams = ref<Record<string, unknown>>({})
const extraParamsOriginalJson = ref('')  // JSON string for dirty comparison / 用于脏检查的 JSON 字符串
const showExtraParamsEditor = ref(false)

// 计算属性：是否有未保存的修改 / Computed: whether there are unsaved changes
const extraParamsEdited = computed(() =>
  JSON.stringify(extraParams.value) !== extraParamsOriginalJson.value
)

// 格式化摘要显示（截断过长的 JSON）/ Format summary for display (truncate long JSON)
const extraParamsSummary = computed(() => {
  const keys = Object.keys(extraParams.value)
  if (keys.length === 0) return '(empty)'
  const json = JSON.stringify(extraParams.value)
  return json.length > 80 ? json.slice(0, 80) + '…' : json
})

// 浏览目录 / Browse directory
async function browseDir(target: 'output') {
  try {
    const dir = await openDirectoryDialog()
    if (dir && target === 'output') outputDir.value = dir
  } catch { /* cancelled */ }
}

// 浏览文件（支持多选）/ Browse file (multi-select)
async function browseFile(target: 'requirement' | 'api') {
  try {
    const files = await openFileDialog(true)
    if (files) {
      const paths = Array.isArray(files) ? files.join(';') : files
      if (target === 'requirement') requirementPaths.value = paths
      else apiPaths.value = paths
    }
  } catch { /* cancelled */ }
}

// 解析路径字符串为数组 / Parse path string to array
function splitPaths(input: string): string[] {
  if (!input.trim()) return []
  return input.split(/[;\n]+/).map(s => s.trim()).filter(Boolean)
}

// 加载配置文件（固定文件名为 env.yaml）/ Load config file (hardcoded filename: env.yaml)
async function loadYamlConfig() {
  if (!agent.config.agentRootDir) {
    configError.value = t('agent.form_agentRootNotSet')
    return
  }
  loadingConfig.value = true
  configError.value = ''
  try {
    const configPath = `${agent.config.agentRootDir}/env.yaml`
    const content = await readFile(configPath)
    const parsed = yaml.load(content) as Record<string, any> | null

    if (!parsed || typeof parsed !== 'object') {
      configError.value = t('agent.form_configInvalid')
      return
    }

    // 提取各节 / Extract sections
    // LLM 配置 — 标量值 / LLM config — scalar values
    if (parsed.llm && typeof parsed.llm === 'object') {
      const llm: Record<string, any> = {}
      for (const [k, v] of Object.entries(parsed.llm as Record<string, unknown>)) {
        if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') {
          llm[k] = v
        }
      }
      llmConfig.value = llm

      // 加载 extra_params 为对象供 JsonEditor 编辑 / Load extra_params as object for JsonEditor
      if (parsed.llm.extra_params && typeof parsed.llm.extra_params === 'object') {
        extraParams.value = parsed.llm.extra_params as Record<string, unknown>
        extraParamsOriginalJson.value = JSON.stringify(extraParams.value)
      } else {
        extraParams.value = {}
        extraParamsOriginalJson.value = '{}'
      }
    }

    // 完整配置数据给 ConfigPanel / Full config for ConfigPanel
    fullConfig.value = {
      pipeline: (parsed.pipeline && typeof parsed.pipeline === 'object') ? parsed.pipeline : {},
      validation: (parsed.validation && typeof parsed.validation === 'object') ? parsed.validation : {},
      plugins: (parsed.plugins && typeof parsed.plugins === 'object') ? parsed.plugins : {},
      skills: (parsed.skills && typeof parsed.skills === 'object') ? parsed.skills : {},
      logging: (parsed.logging && typeof parsed.logging === 'object') ? parsed.logging : {},
    }

    configLoaded.value = true
  } catch (e: any) {
    const msg = e?.message || String(e)
    // 文件不存在 → 友好提示 / File not found → friendly message
    if (msg.includes('os error 2') || msg.includes('No such file') || msg.includes('not found')) {
      configError.value = t('agent.form_configNotFound', { path: 'env.yaml' })
    } else {
      configError.value = msg
    }
  } finally {
    loadingConfig.value = false
  }
}

/**
 * 保存 LLM 配置到 YAML（使用 yaml Document API 原地修改，保留所有注释）。
 * Save LLM config to YAML (in-place modification via yaml Document API; preserves all comments).
 */
async function saveLlmConfig() {
  if (!agent.config.agentRootDir) return
  try {
    const { writeFile } = await import('../../utils/desktop-bridge')
    const configPath = `${agent.config.agentRootDir}/env.yaml`
    const content = await readFile(configPath)

    // 使用 yaml 包解析文档（保留注释和格式）/ Parse with yaml package (preserves comments & formatting)
    const doc = YAML.parseDocument(content)
    let llmNode = doc.get('llm', true) // true = keep as YAMLMap node

    if (!llmNode || !YAML.isMap(llmNode)) {
      llmNode = doc.createMap()
      doc.set('llm', llmNode)
    }

    // 更新标量值 / Update scalar values
    for (const [key, val] of Object.entries(llmConfig.value)) {
      llmNode.set(key, val)
    }

    // 更新 extra_params（如果有编辑，直接使用对象，无需 JSON.parse）/ Update extra_params if edited (use object directly, no JSON.parse needed)
    if (extraParamsEdited.value) {
      llmNode.set('extra_params', extraParams.value)
      extraParamsOriginalJson.value = JSON.stringify(extraParams.value)
    }

    await writeFile(configPath, doc.toString())
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
    message.warning(t('agent.form_outputRequired'))
    return
  }

  const taskId = await agent.createTask({
    outputDir: outputDir.value,
    requirementPaths: requirementPaths.value,
    apiPaths: apiPaths.value,
    autoMode: autoMode.value,
    userGuidance: userGuidance.value,
    caseType: caseType.value,
  })

  // 构建 CLI 覆盖参数 / Build CLI override args
  const cliArgs: string[] = []
  for (const [path, val] of Object.entries(configOverrides.value)) {
    if (val === undefined || val === null || val === '') continue
    const parts = path.split('.')
    const section = parts[0]

    if (section === 'pipeline') {
      const key = parts[1]
      if (key === 'auto') { if (val) cliArgs.push('--auto'); continue }
      if (key === 'case_type') { cliArgs.push('--case-type', String(val)); continue }
      // 跳过 Python 解析器中不存在的参数 / Skip CLI args that don't exist in Python parser
      if (key === 'max_steps_no_progress') continue
      cliArgs.push(`--${key.replace(/_/g, '-')}`, String(val))
    } else if (section === 'validation') {
      // 支持嵌套路径 validation.url_doc_match_validation.enable 等 / Support nested paths
      const fieldPath = parts.slice(1).join('_')
      // url_doc_match_validation.enable → --url-doc-match-enabled / --no-url-doc-match-enabled
      if (fieldPath === 'url_doc_match_validation_enable') {
        cliArgs.push(val ? '--url-doc-match-enabled' : '--no-url-doc-match-enabled')
      } else if (fieldPath === 'url_doc_match_validation_max_retries') {
        cliArgs.push('--url-doc-match-max-retries', String(val))
      }
      // 注意：不存在 --validation/--no-validation 参数 / Note: no --validation/--no-validation flag
    } else if (section === 'plugins') {
      if (parts[1] === 'enabled') {
        cliArgs.push(val ? '--plugins' : '--no-plugins')
      }
      // modules 无 CLI 映射 / modules has no CLI mapping
    } else if (section === 'skills') {
      if (parts[1] === 'enabled') {
        cliArgs.push(val ? '--skills' : '--no-skills')
      }
      // agents 无 CLI 映射 / agents has no CLI mapping
    } else if (section === 'logging' && parts[1] === 'log_to_output' && val) {
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
      <h4>{{ t('agent.form_basicSettings') }}</h4>

      <div class="form-row">
        <label>{{ t('agent.form_outputDir') }} *</label>
        <a-input-group compact>
          <a-input v-model:value="outputDir" style="width: calc(100% - 80px)" :placeholder="t('agent.form_outputDirHint')" />
          <a-button @click="browseDir('output')">{{ t('agent.settings_browse') }}</a-button>
        </a-input-group>
      </div>

      <div class="form-row">
        <label>{{ t('agent.form_requirement') }}</label>
        <a-input-group compact>
          <a-input v-model:value="requirementPaths" style="width: calc(100% - 80px)" :placeholder="t('agent.form_requirementHint')" />
          <a-button @click="browseFile('requirement')">{{ t('agent.settings_browse') }}</a-button>
        </a-input-group>
      </div>

      <div class="form-row">
        <label>{{ t('agent.form_api') }}</label>
        <a-input-group compact>
          <a-input v-model:value="apiPaths" style="width: calc(100% - 80px)" :placeholder="t('agent.form_apiHint')" />
          <a-button @click="browseFile('api')">{{ t('agent.settings_browse') }}</a-button>
        </a-input-group>
      </div>

      <div class="form-row inline">
        <label>{{ t('agent.form_autoMode') }}</label>
        <a-switch v-model:checked="autoMode" size="small" />
      </div>

      <div class="form-row">
        <label>{{ t('agent.form_userGuidance') }}</label>
        <a-textarea v-model:value="userGuidance" :rows="3" :placeholder="t('agent.form_userGuidanceHint')" />
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
        {{ t('agent.form_loadConfig', { name: 'env.yaml' }) }}
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
        <!-- extra_params 编辑（JsonEditor 模态框）/ extra_params editing (JsonEditor modal) -->
        <div class="form-row">
          <label>extra_params
            <span style="color: #999; font-weight: 400; font-size: 11px;">
              ({{ t('agent.form_extraParamsHint') }})
            </span>
          </label>
          <div style="display: flex; align-items: center; gap: 8px;">
            <span class="extra-params-summary">{{ extraParamsSummary }}</span>
            <a-button size="small" @click="showExtraParamsEditor = true">
              {{ t('jsonEditor.editDetails') }}
            </a-button>
          </div>
        </div>
        <a-button size="small" type="primary" @click="saveLlmConfig" style="margin-top: 8px;">
          {{ t('agent.form_llmSave') }}
        </a-button>
      </div>

      <!-- JsonEditor 模态框（extra_params 编辑）/ JsonEditor modal (extra_params editing) -->
      <JsonEditor
        :visible="showExtraParamsEditor"
        :value="extraParams"
        :title="'extra_params'"
        @confirm="(v: Record<string, unknown>) => { extraParams = v; showExtraParamsEditor = false }"
        @cancel="showExtraParamsEditor = false"
      />
    </div>

    <!-- 其他配置 / Other config -->
    <div class="form-section">
      <h4>{{ t('agent.form_otherConfig') }}</h4>
      <ConfigPanel :config-data="fullConfig" @change="handleConfigChange" />
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
}
/* extra_params 摘要显示样式 / extra_params summary display style */
.extra-params-summary {
  font-size: 12px;
  color: #666;
  padding: 4px 8px;
  background: #f5f5f5;
  border-radius: 3px;
  word-break: break-all;
  font-family: monospace;
  flex: 1;
}
</style>
