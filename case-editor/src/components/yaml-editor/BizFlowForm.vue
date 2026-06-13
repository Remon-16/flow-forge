<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useYamlStore } from '../../stores/yaml-store'
import type { BizYamlCase, YamlBizStep } from '../../types/yaml'
import StepEditor from './StepEditor.vue'
import JsonEditor from '../json-editor/JsonEditor.vue'
import AssertRulesModal from '../editor/AssertRulesModal.vue'
import { normalizeJsonValue } from '../../utils/json-helper'

const { t } = useI18n()
const yamlStore = useYamlStore()

const currentCase = computed(() => yamlStore.currentCase as BizYamlCase | null)

function updateSheetName(value: string) {
  yamlStore.updateBizField('sheet_name', value)
}

function addStep() {
  yamlStore.addBizStep()
}

function removeStep(index: number) {
  yamlStore.removeBizStep(index)
}

function moveStep(index: number, direction: 'up' | 'down') {
  yamlStore.moveBizStep(index, direction)
}

function onStepFieldChange(index: number, field: string, value: unknown) {
  yamlStore.updateBizStepField(index, field as keyof YamlBizStep, value)
}

function onStepRulesUpdate(index: number, rules: string[] | null) {
  yamlStore.updateBizStepField(index, 'assert_rules', rules)
}

// JSON editor
const jsonModalVisible = ref(false)
const jsonModalField = ref('')
const jsonModalStep = ref(-1)
const jsonValue = ref<Record<string, unknown>>({})

function openJsonEditor(stepIdx: number, field: string) {
  jsonModalStep.value = stepIdx
  jsonModalField.value = field
  const raw = (currentCase.value!.steps[stepIdx] as unknown as Record<string, unknown>)[field]
  jsonValue.value = normalizeJsonValue(raw)
  jsonModalVisible.value = true
}

function onJsonConfirm(value: Record<string, unknown>) {
  if (jsonModalStep.value >= 0 && jsonModalField.value) {
    yamlStore.updateBizStepField(jsonModalStep.value, jsonModalField.value as keyof YamlBizStep, value)
  }
  jsonModalVisible.value = false
}

// AssertRules editor
const assertRulesModalVisible = ref(false)
const assertRulesModalStep = ref(-1)
const assertRulesValue = ref<string[] | null>(null)

function openAssertRulesEditor(stepIdx: number) {
  assertRulesModalStep.value = stepIdx
  assertRulesValue.value = (currentCase.value!.steps[stepIdx] as unknown as Record<string, unknown>)['assert_rules'] as string[] | null
  assertRulesModalVisible.value = true
}

function onAssertRulesConfirm(rules: string[]) {
  if (assertRulesModalStep.value >= 0) {
    yamlStore.updateBizStepField(assertRulesModalStep.value, 'assert_rules', rules.length > 0 ? rules : null)
  }
  assertRulesModalVisible.value = false
}
</script>

<template>
  <div class="biz-flow-form" v-if="currentCase">
    <div class="biz-flow-header">
      <a-form-item :label="'Sheet Name'" class="sheet-name-input">
        <a-input
          :value="currentCase.sheet_name"
          size="small"
          style="width: 300px;"
          @change="(e: any) => updateSheetName(e.target.value)"
        />
      </a-form-item>
      <a-button type="primary" size="small" @click="addStep">
        + {{ t('table.addStep') }}
      </a-button>
    </div>

    <div class="steps-list">
      <StepEditor
        v-for="(step, i) in (currentCase.steps as (YamlBizStep & any)[])"
        :key="i"
        :step="step"
        :index="i"
        @update="(idx: number, field: string, val: unknown) => onStepFieldChange(idx, field, val)"
        @remove="removeStep"
        @move="moveStep"
        @open-json="openJsonEditor"
        @open-assert-rules="openAssertRulesEditor"
        @update-rules="(idx: number, rules: string[] | null) => onStepRulesUpdate(idx, rules)"
      />

      <div v-if="currentCase.steps.length === 0" class="no-steps">
        {{ t('table.noData') }}
      </div>
    </div>

    <JsonEditor
      :visible="jsonModalVisible"
      :value="jsonValue"
      :title="jsonModalField"
      @confirm="onJsonConfirm"
      @cancel="jsonModalVisible = false"
    />

    <AssertRulesModal
      :visible="assertRulesModalVisible"
      :rules="assertRulesValue"
      @confirm="onAssertRulesConfirm"
      @cancel="assertRulesModalVisible = false"
    />
  </div>
</template>

<style scoped>
.biz-flow-form {
  padding: 16px;
  overflow: auto;
  height: 100%;
}

.biz-flow-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
}

.sheet-name-input {
  margin-bottom: 0;
}

.steps-list {
  display: flex;
  flex-direction: column;
}

.no-steps {
  padding: 24px;
  text-align: center;
  color: #bbb;
}
</style>
