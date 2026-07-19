<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { useAgentStore } from '../../stores/agent'
import { openDirectoryDialog, openFileDialog, readFile } from '../../utils/desktop-bridge'
import { getEditableDestSet, getFlagMap } from '../../utils/cli-schema'
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

// extra_params（textArea 直接编辑 + JsonEditor 可视化编辑）/ extra_params (textArea direct edit + JsonEditor visual edit)
const extraParams = ref<Record<string, unknown>>({})

// ---- YAML 原文编辑（始终可编辑，自动弱校验）/ YAML raw text editing (always editable, auto subtle validation) ----

const extraParamsYamlText = ref('')
const extraParamsYamlError = ref('')
const showExtraParamsEditor = ref(false)

/** 从数据模型同步 YAML 文本 / Sync YAML text from data model */
function syncExtraParamsYamlFromData() {
  extraParamsYamlText.value = yaml.dump(extraParams.value, {
    indent: 2, lineWidth: -1, noRefs: true, sortKeys: false, flowLevel: -1,
  })
  extraParamsYamlError.value = ''
}

/** 自动校验 YAML 语法（弱提示）/ Auto-validate YAML syntax (subtle hint) */
function autoValidateExtraParamsYaml() {
  if (!extraParamsYamlText.value.trim()) {
    extraParamsYamlError.value = ''
    return
  }
  try {
    yaml.load(extraParamsYamlText.value)
    extraParamsYamlError.value = ''
  } catch (e: any) {
    extraParamsYamlError.value = e?.message || String(e)
  }
}

/** 应用 YAML 原文编辑 → 解析并更新 extraParams / Apply YAML raw edit → parse and update extraParams */
function applyExtraParamsYamlEdit() {
  // 空 textarea → 清空 extraParams / Empty textarea → clear extraParams
  if (!extraParamsYamlText.value.trim()) {
    extraParams.value = {}
    syncExtraParamsYamlFromData()
    return
  }
  // 有语法错误时不应用（弱提示已显示给用户）/ Don't apply when syntax error (subtle hint already shown)
  if (extraParamsYamlError.value) return
  try {
    const parsed = yaml.load(extraParamsYamlText.value) as Record<string, unknown>
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return
    extraParams.value = parsed
    syncExtraParamsYamlFromData()
  } catch { /* 语法错误时不做任何事 / do nothing on syntax error */ }
}

// 浏览目录 / Browse directory
async function browseDir(target: 'output') {
  try {
    const dir = await openDirectoryDialog()
    if (dir && target === 'output') outputDir.value = dir.replace(/\\/g, '/')
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
      } else {
        extraParams.value = {}
      }
      syncExtraParamsYamlFromData()
    }

    // 完整配置数据给 ConfigPanel — 仅包含有 CLI 映射的字段 / Full config for ConfigPanel — only CLI-mapped fields
    const pipelineCliDests = getEditableDestSet('agent', 'pipeline')
    const rawPipeline = (parsed.pipeline && typeof parsed.pipeline === 'object')
      ? parsed.pipeline as Record<string, unknown>
      : {}
    fullConfig.value = {
      // 过滤 pipeline：只保留有对应 CLI 参数的字段（如 plan_biz_flow_batch_size 是 settings-only，不显示）
      // Filter pipeline: only keep fields with corresponding CLI args (settings-only keys like plan_biz_flow_batch_size are hidden)
      pipeline: Object.fromEntries(
        Object.entries(rawPipeline).filter(([k]) => pipelineCliDests.has(k))
      ),
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
    // 先应用 textarea 中的 YAML 编辑 / Apply YAML edits from textarea first
    applyExtraParamsYamlEdit()
    const { writeFile } = await import('../../utils/desktop-bridge')
    const configPath = `${agent.config.agentRootDir}/env.yaml`
    const content = await readFile(configPath)

    // 使用 yaml 包解析文档（保留注释和格式）/ Parse with yaml package (preserves comments & formatting)
    const doc = YAML.parseDocument(content)
    let llmNode: YAML.YAMLMap
    const existing = doc.get('llm', true)
    if (existing && YAML.isMap(existing)) {
      llmNode = existing
    } else {
      llmNode = doc.createNode({}) as YAML.YAMLMap
      doc.set('llm', llmNode)
    }

    // 更新标量值 / Update scalar values
    for (const [key, val] of Object.entries(llmConfig.value)) {
      llmNode.set(key, val)
    }

    // 更新 extra_params（applyExtraParamsYamlEdit 已确保值是最新的）
    // Update extra_params (applyExtraParamsYamlEdit ensures value is up-to-date)
    llmNode.set('extra_params', extraParams.value)

    await writeFile(configPath, doc.toString())
    message.success(t('agent.form_llmSaved'))
  } catch (e: any) {
    message.error(e?.message || 'Save failed')
  }
}

/** 深层设置对象属性（点分隔路径）/ Deep-set object property by dot-separated path */
function deepSet(obj: Record<string, any>, path: string, value: any): void {
  const parts = path.split('.')
  let current = obj
  for (let i = 0; i < parts.length - 1; i++) {
    if (!(parts[i] in current) || typeof current[parts[i]] !== 'object') {
      current[parts[i]] = {}
    }
    current = current[parts[i]]
  }
  current[parts[parts.length - 1]] = value
}

// 处理配置覆盖 / Handle config override
function handleConfigChange(path: string, value: any) {
  configOverrides.value[path] = value
  // 同步更新 fullConfig 以便 ConfigPanel 重渲染 / Sync fullConfig for ConfigPanel re-render
  deepSet(fullConfig.value, path, value)
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
  // 从 shared schema 获取 flag 映射（一次性，避免循环内重复构建）
  // Fetch flag maps from shared schema once (avoid rebuilding in loop)
  const pipelineFlagMap = getFlagMap('agent', 'pipeline')

  const cliArgs: string[] = []
  for (const [path, val] of Object.entries(configOverrides.value)) {
    if (val === undefined || val === null || val === '') continue
    const parts = path.split('.')
    const section = parts[0]

    if (section === 'pipeline') {
      const key = parts[1]
      // auto 和 case_type 是布尔标志，仅当为 true 时才添加 / auto and case_type are boolean flags, only add when true
      if (key === 'auto') { if (val) cliArgs.push('--auto'); continue }
      if (key === 'case_type') { cliArgs.push('--case-type', String(val)); continue }
      // 从 shared schema 获取 CLI flag（不在 schema 中的 key 被静默跳过）
      // Look up CLI flag from shared schema (keys not in schema are silently skipped)
      const flag = pipelineFlagMap.get(key)
      if (flag) {
        cliArgs.push(flag, String(val))
      }
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
        <!-- extra_params YAML 原文编辑（始终可编辑，自动弱校验）/ extra_params YAML raw editing (always editable, auto subtle validation) -->
        <div class="form-row">
          <label>extra_params
            <span style="color: #999; font-weight: 400; font-size: 11px;">
              ({{ t('agent.form_extraParamsHint') }})
            </span>
          </label>
          <div class="extra-params-yaml-area">
            <a-textarea
              v-model:value="extraParamsYamlText"
              :rows="10"
              style="font-family: monospace; font-size: 13px;"
              @change="autoValidateExtraParamsYaml"
            />
            <div v-if="extraParamsYamlError" class="yaml-hint">
              ⚠ {{ extraParamsYamlError }}
            </div>
            <div class="yaml-edit-actions">
              <a-button size="small" type="primary" @click="saveLlmConfig">
                {{ t('agent.form_llmSave') }}
              </a-button>
              <a-button size="small" @click="showExtraParamsEditor = true">
                {{ t('jsonEditor.editDetails') }}
              </a-button>
            </div>
          </div>
        </div>

        <!-- JsonEditor 弹窗（可视化编辑）/ JsonEditor modal (visual editing) -->
        <JsonEditor
          :visible="showExtraParamsEditor"
          :value="extraParams"
          :title="'extra_params'"
          @confirm="(v: Record<string, unknown>) => { extraParams = v; showExtraParamsEditor = false; syncExtraParamsYamlFromData(); }"
          @cancel="showExtraParamsEditor = false"
        />
      </div>
    </div>

    <!-- 其他配置 / Other config -->
    <div class="form-section">
      <h4>{{ t('agent.form_otherConfig') }}</h4>
      <ConfigPanel
        :config-data="fullConfig"
        :inline-array-sections="['validation', 'plugins', 'skills']"
        @change="handleConfigChange"
      />
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
/* YAML 原文编辑（始终可编辑）/ YAML raw text editing (always editable) */
.extra-params-yaml-area {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.yaml-edit-actions {
  display: flex;
  gap: 8px;
}
.yaml-hint {
  color: #faad14;
  font-size: 12px;
}
</style>
