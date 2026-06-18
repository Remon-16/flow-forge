<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useYamlStore } from '../../stores/yaml-store'
import { TAG_LEVELS, HTTP_METHODS } from '../../types/excel'
import type { SingleYamlCase } from '../../types/yaml'
import JsonEditor from '../json-editor/JsonEditor.vue'
import AssertRulesModal from '../editor/AssertRulesModal.vue'
import ProcessorListEditor from '../editor/ProcessorListEditor.vue'
import { normalizeJsonValue } from '../../utils/json-helper'

const { t } = useI18n()
const yamlStore = useYamlStore()

const currentCase = computed(() => yamlStore.currentCase as SingleYamlCase | null)

const isUrlWarning = computed(() =>
  (currentCase.value?.url || '').includes('<URL not exist>')
)

// Clear inline cache when currentCase changes externally (e.g. from YAML raw view replace)
watch(() => yamlStore.currentCase, () => {
  jsonEditCache.value = {}
  rulesEditText.value = ''
})

function updateField(field: string, value: unknown) {
  yamlStore.updateSingleField(field as keyof SingleYamlCase, value)
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
  if (field in jsonEditCache.value) return jsonEditCache.value[field]
  return formatJson(value)
}

function onJsonEditChange(field: string, text: string) {
  jsonEditCache.value = { ...jsonEditCache.value, [field]: text }
}

function onJsonEditBlur(field: string) {
  if (!(field in jsonEditCache.value)) return
  const text = (jsonEditCache.value[field] || '').trim()
  if (!text) {
    updateField(field, null)
    delete jsonEditCache.value[field]
    return
  }
  try {
    const parsed = JSON.parse(text)
    updateField(field, parsed)
    delete jsonEditCache.value[field]
  } catch {
    // Keep cache so user can fix, but don't update store
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
    updateField('assert_rules', null)
    rulesEditText.value = ''
    return
  }
  const rules = text.split('\n').map(r => r.trim()).filter(r => r.length > 0)
  updateField('assert_rules', rules)
  rulesEditText.value = ''
}

// JSON editor modal
const jsonModalVisible = ref(false)
const jsonModalField = ref('')
const jsonValue = ref<Record<string, unknown>>({})

function openJsonEditor(field: string) {
  jsonModalField.value = field
  const raw = (currentCase.value as unknown as Record<string, unknown>)[field]
  jsonValue.value = normalizeJsonValue(raw)
  jsonModalVisible.value = true
}

function onJsonConfirm(value: Record<string, unknown>) {
  if (jsonModalField.value) {
    updateField(jsonModalField.value, value)
  }
  jsonModalVisible.value = false
}

// AssertRules editor modal
const assertRulesModalVisible = ref(false)

function openAssertRulesEditor() {
  assertRulesModalVisible.value = true
}

function onAssertRulesConfirm(rules: string[]) {
  updateField('assert_rules', rules.length > 0 ? rules : null)
  assertRulesModalVisible.value = false
}
</script>

<template>
  <div class="single-case-form" v-if="currentCase">
    <a-form layout="vertical" :model="currentCase" size="small">
      <!-- Row 1: TestID + RelevanceID -->
      <a-row :gutter="16">
        <a-col :span="12">
          <a-form-item :label="t('table.TestID')">
            <a-input
              :value="currentCase.test_id"
              @change="(e: any) => updateField('test_id', e.target.value)"
            />
          </a-form-item>
        </a-col>
        <a-col :span="12">
          <a-form-item :label="t('table.RelevanceID')">
            <a-input
              :value="currentCase.relevance_id"
              @change="(e: any) => updateField('relevance_id', e.target.value)"
            />
          </a-form-item>
        </a-col>
      </a-row>

      <!-- Row 2: Tag + APIName -->
      <a-row :gutter="16">
        <a-col :span="12">
          <a-form-item :label="t('table.Tag')">
            <a-select
              :value="currentCase.tag"
              @change="(v: string) => updateField('tag', v)"
            >
              <a-select-option v-for="tag in TAG_LEVELS" :key="tag" :value="tag">
                {{ tag }}
              </a-select-option>
            </a-select>
          </a-form-item>
        </a-col>
        <a-col :span="12">
          <a-form-item :label="t('table.APIName')">
            <a-input
              :value="currentCase.api_name"
              @change="(e: any) => updateField('api_name', e.target.value)"
            />
          </a-form-item>
        </a-col>
      </a-row>

      <!-- Row 3: AppName + Method -->
      <a-row :gutter="16">
        <a-col :span="12">
          <a-form-item :label="t('table.AppName')">
            <a-input
              :value="currentCase.app_name"
              @change="(e: any) => updateField('app_name', e.target.value)"
            />
          </a-form-item>
        </a-col>
        <a-col :span="12">
          <a-form-item :label="t('table.Method')">
            <a-select
              :value="currentCase.method"
              @change="(v: string) => updateField('method', v)"
            >
              <a-select-option v-for="m in HTTP_METHODS" :key="m" :value="m">
                {{ m }}
              </a-select-option>
            </a-select>
          </a-form-item>
        </a-col>
      </a-row>

      <!-- Row 4: URL + StatusCode -->
      <a-row :gutter="16">
        <a-col :span="12">
          <a-form-item :label="t('table.URL')">
            <a-input
              :value="currentCase.url"
              :status="isUrlWarning ? 'error' : ''"
              @change="(e: any) => updateField('url', e.target.value)"
            >
              <template v-if="isUrlWarning" #suffix>
                <a-tooltip :title="t('validator.urlWarning')">
                  <span style="color: #ff4d4f; font-weight: bold;">&#10007;</span>
                </a-tooltip>
              </template>
            </a-input>
          </a-form-item>
        </a-col>
        <a-col :span="12">
          <a-form-item :label="t('table.StatusCode')">
            <a-input
              :value="String(currentCase.status_code ?? '')"
              @change="(e: any) => updateField('status_code', e.target.value)"
            />
          </a-form-item>
        </a-col>
      </a-row>

      <!-- RequestHead (full width) -->
      <a-row :gutter="16">
        <a-col :span="24">
          <a-form-item>
            <template #label>
              <span>{{ t('table.RequestHead') }}</span>
              <a-button
                size="small"
                type="link"
                style="padding: 0 0 0 8px; font-size: 12px;"
                @click="openJsonEditor('request_head')"
              >
                {{ t('jsonEditor.editDetails') }}
              </a-button>
            </template>
            <a-textarea
              :value="getJsonEditText('request_head', currentCase.request_head)"
              :auto-size="{ minRows: 2, maxRows: 12 }"
              :placeholder="t('jsonEditor.noData')"
              @change="(e: any) => onJsonEditChange('request_head', e.target.value)"
              @blur="() => onJsonEditBlur('request_head')"
            />
          </a-form-item>
        </a-col>
      </a-row>

      <!-- RequestBody (full width) -->
      <a-row :gutter="16">
        <a-col :span="24">
          <a-form-item>
            <template #label>
              <span>{{ t('table.RequestBody') }}</span>
              <a-button
                size="small"
                type="link"
                style="padding: 0 0 0 8px; font-size: 12px;"
                @click="openJsonEditor('request_body')"
              >
                {{ t('jsonEditor.editDetails') }}
              </a-button>
            </template>
            <a-textarea
              :value="getJsonEditText('request_body', currentCase.request_body)"
              :auto-size="{ minRows: 2, maxRows: 12 }"
              :placeholder="t('jsonEditor.noData')"
              @change="(e: any) => onJsonEditChange('request_body', e.target.value)"
              @blur="() => onJsonEditBlur('request_body')"
            />
          </a-form-item>
        </a-col>
      </a-row>

      <!-- AssertDict (full width) -->
      <a-row :gutter="16">
        <a-col :span="24">
          <a-form-item>
            <template #label>
              <span>{{ t('table.AssertDict') }}</span>
              <a-button
                size="small"
                type="link"
                style="padding: 0 0 0 8px; font-size: 12px;"
                @click="openJsonEditor('assert_dict')"
              >
                {{ t('jsonEditor.editDetails') }}
              </a-button>
            </template>
            <a-textarea
              :value="getJsonEditText('assert_dict', currentCase.assert_dict)"
              :auto-size="{ minRows: 2, maxRows: 12 }"
              :placeholder="t('jsonEditor.noData')"
              @change="(e: any) => onJsonEditChange('assert_dict', e.target.value)"
              @blur="() => onJsonEditBlur('assert_dict')"
            />
          </a-form-item>
        </a-col>
      </a-row>

      <!-- AssertRules (full width) -->
      <a-row :gutter="16">
        <a-col :span="24">
          <a-form-item>
            <template #label>
              <span>{{ t('assertRules.title') }}</span>
              <a-button
                size="small"
                type="link"
                style="padding: 0 0 0 8px; font-size: 12px;"
                @click="openAssertRulesEditor"
              >
                {{ t('assertRules.editDetails') }}
              </a-button>
            </template>
            <a-textarea
              :value="getRulesEditText(currentCase.assert_rules)"
              :auto-size="{ minRows: 2, maxRows: 12 }"
              :placeholder="t('assertRules.empty')"
              @change="(e: any) => onRulesEditChange(e.target.value)"
              @blur="onRulesEditBlur"
            />
          </a-form-item>
        </a-col>
      </a-row>

      <!-- PreProcessors (full width) -->
      <a-row :gutter="16">
        <a-col :span="24">
          <a-form-item :label="t('table.PreProcessors')">
            <ProcessorListEditor
              :modelValue="currentCase.preprocessors"
              :title="t('table.PreProcessors')"
              @update:modelValue="(v: any) => updateField('preprocessors', v)"
            />
          </a-form-item>
        </a-col>
      </a-row>

      <!-- PostProcessors (full width) -->
      <a-row :gutter="16">
        <a-col :span="24">
          <a-form-item :label="t('table.PostProcessors')">
            <ProcessorListEditor
              :modelValue="currentCase.postprocessors"
              :title="t('table.PostProcessors')"
              @update:modelValue="(v: any) => updateField('postprocessors', v)"
            />
          </a-form-item>
        </a-col>
      </a-row>

      <!-- Remark (full width) -->
      <a-row :gutter="16">
        <a-col :span="24">
          <a-form-item :label="t('table.Remark')">
            <a-textarea
              :value="currentCase.remark"
              :auto-size="{ minRows: 2, maxRows: 8 }"
              @change="(e: any) => updateField('remark', e.target.value)"
            />
          </a-form-item>
        </a-col>
      </a-row>
    </a-form>

    <!-- JSON Editor Modal -->
    <JsonEditor
      :visible="jsonModalVisible"
      :value="jsonValue"
      :title="jsonModalField"
      @confirm="onJsonConfirm"
      @cancel="jsonModalVisible = false"
    />

    <!-- AssertRules Editor Modal -->
    <AssertRulesModal
      :visible="assertRulesModalVisible"
      :rules="currentCase.assert_rules"
      @confirm="onAssertRulesConfirm"
      @cancel="assertRulesModalVisible = false"
    />
  </div>
</template>

<style scoped>
.single-case-form {
  padding: 16px;
}
</style>
