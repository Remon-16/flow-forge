<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useYamlStore } from '../../stores/yaml-store'
import { TAG_LEVELS, HTTP_METHODS } from '../../types/excel'
import type { SingleYamlCase } from '../../types/yaml'
import JsonEditor from '../json-editor/JsonEditor.vue'
import AssertRulesModal from '../editor/AssertRulesModal.vue'
import { normalizeJsonValue } from '../../utils/json-helper'

const { t } = useI18n()
const yamlStore = useYamlStore()

const currentCase = computed(() => yamlStore.currentCase as SingleYamlCase | null)

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

// JSON editor
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

// AssertRules editor
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
              @change="(e: any) => updateField('url', e.target.value)"
            />
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
              :value="formatJson(currentCase.request_head)"
              :auto-size="{ minRows: 2, maxRows: 12 }"
              readonly
              :placeholder="t('jsonEditor.noData')"
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
              :value="formatJson(currentCase.request_body)"
              :auto-size="{ minRows: 2, maxRows: 12 }"
              readonly
              :placeholder="t('jsonEditor.noData')"
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
              :value="formatJson(currentCase.assert_dict)"
              :auto-size="{ minRows: 2, maxRows: 12 }"
              readonly
              :placeholder="t('jsonEditor.noData')"
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
              :value="formatRules(currentCase.assert_rules)"
              :auto-size="{ minRows: 2, maxRows: 12 }"
              readonly
              :placeholder="t('assertRules.empty')"
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
  overflow: auto;
  height: 100%;
}
</style>
