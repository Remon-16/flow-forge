<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useYamlStore } from '../../stores/yaml-store'
import { TAG_LEVELS, HTTP_METHODS } from '../../types/excel'
import type { YamlBizStep } from '../../types/yaml'

const { t } = useI18n()
const yamlStore = useYamlStore()

// Clear inline cache when currentCase changes externally (e.g. from YAML raw view replace)
watch(() => yamlStore.currentCase, () => {
  jsonEditCache.value = {}
  rulesEditText.value = ''
})

const props = defineProps<{
  step: YamlBizStep & { _stepIdDuplicate?: boolean; _transError?: string | null }
  index: number
}>()

const isUrlWarning = computed(() =>
  ((props.step as any).url || '').includes('<URL not exist>')
)

const emit = defineEmits<{
  (e: 'update', index: number, field: string, value: unknown): void
  (e: 'remove', index: number): void
  (e: 'move', index: number, direction: 'up' | 'down'): void
  (e: 'openJson', index: number, field: string): void
  (e: 'openAssertRules', index: number): void
  (e: 'updateRules', index: number, rules: string[] | null): void
}>()

function onFieldChange(field: string, value: unknown) {
  emit('update', props.index, field, value)
}

function formatJson(val: unknown): string {
  if (!val) return ''
  try {
    return JSON.stringify(val, null, 2)
  } catch {
    return String(val)
  }
}

function formatRules(val: string[] | null): string {
  if (!val || val.length === 0) return ''
  return val.join('\n')
}

// Inline JSON editing cache
const jsonEditCache = ref<Record<string, string>>({})

function getJsonEditText(field: string, value: unknown): string {
  const key = `${props.index}_${field}`
  if (key in jsonEditCache.value) return jsonEditCache.value[key]
  return formatJson(value)
}

function onJsonEditChange(field: string, text: string) {
  const key = `${props.index}_${field}`
  jsonEditCache.value = { ...jsonEditCache.value, [key]: text }
}

function onJsonEditBlur(field: string) {
  const key = `${props.index}_${field}`
  if (!(key in jsonEditCache.value)) return
  const text = (jsonEditCache.value[key] || '').trim()
  if (!text) {
    emit('update', props.index, field, null)
    delete jsonEditCache.value[key]
    return
  }
  try {
    const parsed = JSON.parse(text)
    emit('update', props.index, field, parsed)
    delete jsonEditCache.value[key]
  } catch {
    // Keep cache so user can fix
  }
}

// Inline assert rules editing
const rulesEditText = ref('')

function getRulesEditText(val: string[] | null): string {
  if (rulesEditText.value) return rulesEditText.value
  return formatRules(val)
}

function onRulesEditChange(text: string) {
  rulesEditText.value = text
}

function onRulesEditBlur() {
  if (!rulesEditText.value) return
  const text = rulesEditText.value.trim()
  if (!text) {
    emit('updateRules', props.index, null)
    rulesEditText.value = ''
    return
  }
  const rules = text.split('\n').map(r => r.trim()).filter(r => r.length > 0)
  emit('updateRules', props.index, rules)
  rulesEditText.value = ''
}
</script>

<template>
  <div class="step-editor">
    <div class="step-header">
      <span class="step-title">Step {{ index + 1 }}</span>
      <div class="step-actions">
        <a-button size="small" type="text" @click="emit('move', index, 'up')" :disabled="index === 0">
          &#8593;
        </a-button>
        <a-button size="small" type="text" @click="emit('move', index, 'down')">
          &#8595;
        </a-button>
        <a-button size="small" type="text" danger @click="emit('remove', index)">
          &times;
        </a-button>
      </div>
    </div>

    <!-- Row 1: StepID + RelevanceID -->
    <a-row :gutter="12">
      <a-col :span="12">
        <a-form-item :label="t('table.StepID')" class="compact-item">
          <a-input
            :value="step.step_id"
            size="small"
            :status="step._stepIdDuplicate ? 'error' : ''"
            @change="(e: any) => onFieldChange('step_id', e.target.value)"
          >
            <template v-if="step._stepIdDuplicate" #suffix>
              <a-tooltip :title="t('validator.stepIdDuplicate')">
                <span style="color: #ff4d4f;">!</span>
              </a-tooltip>
            </template>
          </a-input>
        </a-form-item>
      </a-col>
      <a-col :span="12">
        <a-form-item :label="t('table.RelevanceID')" class="compact-item">
          <a-input
            :value="step.relevance_id"
            size="small"
            @change="(e: any) => onFieldChange('relevance_id', e.target.value)"
          />
        </a-form-item>
      </a-col>
    </a-row>

    <!-- Row 2: Tag + Trans -->
    <a-row :gutter="12">
      <a-col :span="12">
        <a-form-item :label="t('table.Tag')" class="compact-item">
          <a-select
            :value="step.tag"
            size="small"
            @change="(v: string) => onFieldChange('tag', v)"
          >
            <a-select-option v-for="tag in TAG_LEVELS" :key="tag" :value="tag">
              {{ tag }}
            </a-select-option>
          </a-select>
        </a-form-item>
      </a-col>
      <a-col :span="12">
        <a-form-item :label="t('table.Trans')" class="compact-item">
          <a-tooltip :title="step._transError || ''">
            <a-input
              :value="step.trans"
              size="small"
              :status="step._transError ? 'error' : ''"
              @change="(e: any) => onFieldChange('trans', e.target.value)"
            />
          </a-tooltip>
        </a-form-item>
      </a-col>
    </a-row>

    <!-- Row 3: APIName + Method -->
    <a-row :gutter="12">
      <a-col :span="12">
        <a-form-item :label="t('table.APIName')" class="compact-item">
          <a-input
            :value="step.api_name"
            size="small"
            @change="(e: any) => onFieldChange('api_name', e.target.value)"
          />
        </a-form-item>
      </a-col>
      <a-col :span="12">
        <a-form-item :label="t('table.Method')" class="compact-item">
          <a-select
            :value="step.method"
            size="small"
            @change="(v: string) => onFieldChange('method', v)"
          >
            <a-select-option v-for="m in HTTP_METHODS" :key="m" :value="m">
              {{ m }}
            </a-select-option>
          </a-select>
        </a-form-item>
      </a-col>
    </a-row>

    <!-- Row 4: AppName + URL -->
    <a-row :gutter="12">
      <a-col :span="12">
        <a-form-item :label="t('table.AppName')" class="compact-item">
          <a-input
            :value="step.app_name"
            size="small"
            @change="(e: any) => onFieldChange('app_name', e.target.value)"
          />
        </a-form-item>
      </a-col>
      <a-col :span="12">
        <a-form-item :label="t('table.URL')" class="compact-item">
          <a-input
            :value="step.url"
            size="small"
            :status="isUrlWarning ? 'error' : ''"
            @change="(e: any) => onFieldChange('url', e.target.value)"
          >
            <template v-if="isUrlWarning" #suffix>
              <a-tooltip :title="t('validator.urlWarning')">
                <span style="color: #ff4d4f; font-weight: bold; font-size: 12px;">&#10007;</span>
              </a-tooltip>
            </template>
          </a-input>
        </a-form-item>
      </a-col>
    </a-row>

    <!-- Row 5: StatusCode + Remark -->
    <a-row :gutter="12">
      <a-col :span="12">
        <a-form-item :label="t('table.StatusCode')" class="compact-item">
          <a-input
            :value="String(step.status_code ?? '')"
            size="small"
            @change="(e: any) => onFieldChange('status_code', e.target.value)"
          />
        </a-form-item>
      </a-col>
      <a-col :span="12">
        <a-form-item :label="t('table.Remark')" class="compact-item">
          <a-input
            :value="step.remark"
            size="small"
            @change="(e: any) => onFieldChange('remark', e.target.value)"
          />
        </a-form-item>
      </a-col>
    </a-row>

    <!-- RequestHead (full width) -->
    <a-row :gutter="12">
      <a-col :span="24">
        <a-form-item class="compact-item">
          <template #label>
            <span>{{ t('table.RequestHead') }}</span>
            <a-button
              size="small"
              type="link"
              style="padding: 0 0 0 8px; font-size: 11px;"
              @click="emit('openJson', index, 'request_head')"
            >
              {{ t('jsonEditor.editDetails') }}
            </a-button>
          </template>
          <a-textarea
            :value="getJsonEditText('request_head', step.request_head)"
            :auto-size="{ minRows: 2, maxRows: 8 }"
            size="small"
            :placeholder="t('jsonEditor.noData')"
            @change="(e: any) => onJsonEditChange('request_head', e.target.value)"
            @blur="() => onJsonEditBlur('request_head')"
          />
        </a-form-item>
      </a-col>
    </a-row>

    <!-- RequestBody (full width) -->
    <a-row :gutter="12">
      <a-col :span="24">
        <a-form-item class="compact-item">
          <template #label>
            <span>{{ t('table.RequestBody') }}</span>
            <a-button
              size="small"
              type="link"
              style="padding: 0 0 0 8px; font-size: 11px;"
              @click="emit('openJson', index, 'request_body')"
            >
              {{ t('jsonEditor.editDetails') }}
            </a-button>
          </template>
          <a-textarea
            :value="getJsonEditText('request_body', step.request_body)"
            :auto-size="{ minRows: 2, maxRows: 8 }"
            size="small"
            :placeholder="t('jsonEditor.noData')"
            @change="(e: any) => onJsonEditChange('request_body', e.target.value)"
            @blur="() => onJsonEditBlur('request_body')"
          />
        </a-form-item>
      </a-col>
    </a-row>

    <!-- AssertDict (full width) -->
    <a-row :gutter="12">
      <a-col :span="24">
        <a-form-item class="compact-item">
          <template #label>
            <span>{{ t('table.AssertDict') }}</span>
            <a-button
              size="small"
              type="link"
              style="padding: 0 0 0 8px; font-size: 11px;"
              @click="emit('openJson', index, 'assert_dict')"
            >
              {{ t('jsonEditor.editDetails') }}
            </a-button>
          </template>
          <a-textarea
            :value="getJsonEditText('assert_dict', step.assert_dict)"
            :auto-size="{ minRows: 2, maxRows: 8 }"
            size="small"
            :placeholder="t('jsonEditor.noData')"
            @change="(e: any) => onJsonEditChange('assert_dict', e.target.value)"
            @blur="() => onJsonEditBlur('assert_dict')"
          />
        </a-form-item>
      </a-col>
    </a-row>

    <!-- AssertRules (full width) -->
    <a-row :gutter="12">
      <a-col :span="24">
        <a-form-item class="compact-item">
          <template #label>
            <span>{{ t('assertRules.title') }}</span>
            <a-button
              size="small"
              type="link"
              style="padding: 0 0 0 8px; font-size: 11px;"
              @click="emit('openAssertRules', index)"
            >
              {{ t('assertRules.editDetails') }}
            </a-button>
          </template>
          <a-textarea
            :value="getRulesEditText(step.assert_rules)"
            :auto-size="{ minRows: 2, maxRows: 8 }"
            size="small"
            :placeholder="t('assertRules.empty')"
            @change="(e: any) => onRulesEditChange(e.target.value)"
            @blur="onRulesEditBlur"
          />
        </a-form-item>
      </a-col>
    </a-row>
  </div>
</template>

<style scoped>
.step-editor {
  padding: 12px;
  border: 1px solid #e8e8e8;
  border-radius: 6px;
  margin-bottom: 8px;
  background: #fafafa;
}

.step-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.step-title {
  font-weight: 600;
  font-size: 13px;
}

.step-actions {
  display: flex;
  gap: 4px;
}

.compact-item {
  margin-bottom: 8px;
}

.compact-item :deep(.ant-form-item-label) {
  padding-bottom: 0;
}

.compact-item :deep(.ant-form-item-label > label) {
  font-size: 11px;
  height: auto;
}
</style>
