<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useYamlStore } from '../../stores/yaml-store'
import { TAG_LEVELS, HTTP_METHODS } from '../../types/excel'
import type { SingleYamlCase } from '../../types/yaml'
import AssertRulesEditor from '../editor/AssertRulesEditor.vue'
import JsonEditor from '../json-editor/JsonEditor.vue'
import { normalizeJsonValue } from '../../utils/json-helper'

const { t } = useI18n()
const yamlStore = useYamlStore()

const currentCase = computed(() => yamlStore.currentCase as SingleYamlCase | null)

function updateField(field: string, value: unknown) {
  yamlStore.updateSingleField(field as keyof SingleYamlCase, value)
}

// JSON editor state
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

import { ref } from 'vue'
</script>

<template>
  <div class="single-case-form" v-if="currentCase">
    <a-form layout="vertical" :model="currentCase" size="small">
      <a-row :gutter="16">
        <!-- Row 1 -->
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

        <!-- Row 2 -->
        <a-col :span="8">
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
        <a-col :span="8">
          <a-form-item :label="t('table.APIName')">
            <a-input
              :value="currentCase.api_name"
              @change="(e: any) => updateField('api_name', e.target.value)"
            />
          </a-form-item>
        </a-col>
        <a-col :span="8">
          <a-form-item :label="t('table.AppName')">
            <a-input
              :value="currentCase.app_name"
              @change="(e: any) => updateField('app_name', e.target.value)"
            />
          </a-form-item>
        </a-col>

        <!-- Row 3 -->
        <a-col :span="8">
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
        <a-col :span="16">
          <a-form-item :label="t('table.URL')">
            <a-input
              :value="currentCase.url"
              @change="(e: any) => updateField('url', e.target.value)"
            />
          </a-form-item>
        </a-col>

        <!-- Row 4: JSON fields -->
        <a-col :span="8">
          <a-form-item :label="t('table.StatusCode')">
            <a-input
              :value="String(currentCase.status_code ?? '')"
              @change="(e: any) => updateField('status_code', e.target.value)"
            />
          </a-form-item>
        </a-col>
        <a-col :span="7">
          <a-form-item :label="t('table.RequestHead')">
            <a-button size="small" block @click="openJsonEditor('request_head')">
              {{ t('jsonEditor.details') }}
            </a-button>
          </a-form-item>
        </a-col>
        <a-col :span="9">
          <a-form-item :label="t('table.RequestBody')">
            <a-button size="small" block @click="openJsonEditor('request_body')">
              {{ t('jsonEditor.details') }}
            </a-button>
          </a-form-item>
        </a-col>

        <!-- Row 5: AssertDict and AssertRules -->
        <a-col :span="8">
          <a-form-item :label="t('table.AssertDict')">
            <a-button size="small" block @click="openJsonEditor('assert_dict')">
              {{ t('jsonEditor.details') }}
            </a-button>
          </a-form-item>
        </a-col>
        <a-col :span="16">
          <a-form-item :label="t('assertRules.title')">
            <AssertRulesEditor
              :modelValue="currentCase.assert_rules"
              @update:modelValue="(v: string[] | null) => updateField('assert_rules', v)"
            />
          </a-form-item>
        </a-col>

        <!-- Row 6: Remark -->
        <a-col :span="24">
          <a-form-item :label="t('table.Remark')">
            <a-textarea
              :value="currentCase.remark"
              :rows="2"
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
  </div>
</template>

<style scoped>
.single-case-form {
  padding: 16px;
  overflow: auto;
  height: 100%;
}
</style>
