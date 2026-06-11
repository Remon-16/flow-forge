<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { TAG_LEVELS, HTTP_METHODS } from '../../types/excel'
import type { YamlBizStep } from '../../types/yaml'
import AssertRulesEditor from '../editor/AssertRulesEditor.vue'

const { t } = useI18n()

const props = defineProps<{
  step: YamlBizStep & { _stepIdDuplicate?: boolean; _transError?: string | null }
  index: number
}>()

const emit = defineEmits<{
  (e: 'update', index: number, field: string, value: unknown): void
  (e: 'remove', index: number): void
  (e: 'move', index: number, direction: 'up' | 'down'): void
  (e: 'openJson', index: number, field: string): void
}>()

function onFieldChange(field: string, value: unknown) {
  emit('update', props.index, field, value)
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

    <a-row :gutter="12">
      <a-col :span="6">
        <a-form-item :label="t('table.StepID')" class="compact-item">
          <a-input
            :value="step.StepID"
            size="small"
            :status="step._stepIdDuplicate ? 'error' : ''"
            @change="(e: any) => onFieldChange('StepID', e.target.value)"
          >
            <template v-if="step._stepIdDuplicate" #suffix>
              <a-tooltip :title="t('validator.stepIdDuplicate')">
                <span style="color: #ff4d4f;">!</span>
              </a-tooltip>
            </template>
          </a-input>
        </a-form-item>
      </a-col>
      <a-col :span="6">
        <a-form-item :label="t('table.RelevanceID')" class="compact-item">
          <a-input
            :value="step.RelevanceID"
            size="small"
            @change="(e: any) => onFieldChange('RelevanceID', e.target.value)"
          />
        </a-form-item>
      </a-col>
      <a-col :span="6">
        <a-form-item :label="t('table.Tag')" class="compact-item">
          <a-select
            :value="step.Tag"
            size="small"
            @change="(v: string) => onFieldChange('Tag', v)"
          >
            <a-select-option v-for="tag in TAG_LEVELS" :key="tag" :value="tag">
              {{ tag }}
            </a-select-option>
          </a-select>
        </a-form-item>
      </a-col>
      <a-col :span="6">
        <a-form-item :label="t('table.Trans')" class="compact-item">
          <a-tooltip :title="step._transError || ''">
            <a-input
              :value="step.Trans"
              size="small"
              :status="step._transError ? 'error' : ''"
              @change="(e: any) => onFieldChange('Trans', e.target.value)"
            />
          </a-tooltip>
        </a-form-item>
      </a-col>
    </a-row>

    <a-row :gutter="12">
      <a-col :span="6">
        <a-form-item :label="t('table.APIName')" class="compact-item">
          <a-input
            :value="step.APIName"
            size="small"
            @change="(e: any) => onFieldChange('APIName', e.target.value)"
          />
        </a-form-item>
      </a-col>
      <a-col :span="6">
        <a-form-item :label="t('table.AppName')" class="compact-item">
          <a-input
            :value="step.AppName"
            size="small"
            @change="(e: any) => onFieldChange('AppName', e.target.value)"
          />
        </a-form-item>
      </a-col>
      <a-col :span="4">
        <a-form-item :label="t('table.Method')" class="compact-item">
          <a-select
            :value="step.Method"
            size="small"
            @change="(v: string) => onFieldChange('Method', v)"
          >
            <a-select-option v-for="m in HTTP_METHODS" :key="m" :value="m">
              {{ m }}
            </a-select-option>
          </a-select>
        </a-form-item>
      </a-col>
      <a-col :span="8">
        <a-form-item :label="t('table.URL')" class="compact-item">
          <a-input
            :value="step.URL"
            size="small"
            @change="(e: any) => onFieldChange('URL', e.target.value)"
          />
        </a-form-item>
      </a-col>
    </a-row>

    <a-row :gutter="12">
      <a-col :span="4">
        <a-form-item :label="t('table.StatusCode')" class="compact-item">
          <a-input
            :value="String(step.StatusCode ?? '')"
            size="small"
            @change="(e: any) => onFieldChange('StatusCode', e.target.value)"
          />
        </a-form-item>
      </a-col>
      <a-col :span="5">
        <a-form-item :label="t('table.RequestHead')" class="compact-item">
          <a-button size="small" block @click="emit('openJson', index, 'RequestHead')">
            {{ t('jsonEditor.details') }}
          </a-button>
        </a-form-item>
      </a-col>
      <a-col :span="5">
        <a-form-item :label="t('table.RequestBody')" class="compact-item">
          <a-button size="small" block @click="emit('openJson', index, 'RequestBody')">
            {{ t('jsonEditor.details') }}
          </a-button>
        </a-form-item>
      </a-col>
      <a-col :span="5">
        <a-form-item :label="t('table.AssertDict')" class="compact-item">
          <a-button size="small" block @click="emit('openJson', index, 'AssertDict')">
            {{ t('jsonEditor.details') }}
          </a-button>
        </a-form-item>
      </a-col>
      <a-col :span="5">
        <a-form-item :label="t('table.Remark')" class="compact-item">
          <a-input
            :value="step.Remark"
            size="small"
            @change="(e: any) => onFieldChange('Remark', e.target.value)"
          />
        </a-form-item>
      </a-col>
    </a-row>

    <a-row>
      <a-col :span="24">
        <a-form-item :label="t('assertRules.title')" class="compact-item">
          <AssertRulesEditor
            :modelValue="step.AssertRules"
            @update:modelValue="(v: string[] | null) => onFieldChange('AssertRules', v)"
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
