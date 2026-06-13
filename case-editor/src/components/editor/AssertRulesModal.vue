<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { validateAssertRule } from '../../utils/assert-rules-validator'

const { t } = useI18n()

const props = defineProps<{
  visible: boolean
  rules: string[] | null
}>()

const emit = defineEmits<{
  (e: 'confirm', rules: string[]): void
  (e: 'cancel'): void
}>()

const OPERATORS = [
  { value: '==', label: '==', needsExpected: true },
  { value: '!=', label: '!=', needsExpected: true },
  { value: '>', label: '>', needsExpected: true },
  { value: '<', label: '<', needsExpected: true },
  { value: '>=', label: '>=', needsExpected: true },
  { value: '<=', label: '<=', needsExpected: true },
  { value: '=~', label: '=~ (regex)', needsExpected: true },
  { value: 'contains', label: 'contains', needsExpected: true },
  { value: 'not_contains', label: 'not_contains', needsExpected: true },
  { value: 'in', label: 'in', needsExpected: true },
  { value: 'typeof', label: 'typeof', needsExpected: true },
  { value: 'is_null', label: 'is_null', needsExpected: false },
  { value: 'is_not_null', label: 'is_not_null', needsExpected: false },
]

interface RuleRow {
  path: string
  operator: string
  expected: string
  raw: string
  error: string | null
}

const rows = ref<RuleRow[]>([])

watch(
  () => props.visible,
  (v) => {
    if (v) {
      const list = props.rules || []
      rows.value = list.map((r) => {
        const parsed = validateAssertRule(r)
        return {
          path: parsed.path || '',
          operator: parsed.operator || '',
          expected: parsed.expected || '',
          raw: r,
          error: null,
        }
      })
    }
  },
  { immediate: true }
)

function onPathChange(index: number, value: string) {
  rows.value[index].path = value
  validateRow(index)
}

function onOperatorChange(index: number, value: string) {
  rows.value[index].operator = value
  if (!OPERATORS.find((o) => o.value === value)?.needsExpected) {
    rows.value[index].expected = ''
  }
  validateRow(index)
}

function onExpectedChange(index: number, value: string) {
  rows.value[index].expected = value
  validateRow(index)
}

function validateRow(index: number) {
  const row = rows.value[index]
  const op = OPERATORS.find((o) => o.value === row.operator)
  const needsExpected = op?.needsExpected ?? true
  const ruleStr = needsExpected
    ? `${row.path} ${row.operator} ${row.expected}`
    : `${row.path} ${row.operator}`
  const result = validateAssertRule(ruleStr)
  row.error = result.error
  row.raw = ruleStr
}

function addRule() {
  rows.value.push({ path: '', operator: '==', expected: '', raw: '', error: null })
}

function removeRule(index: number) {
  rows.value.splice(index, 1)
}

function batchPaste() {
  const text = prompt(t('assertRules.batchPasteHint'))
  if (!text) return
  const lines = text.split(/\n/).filter((l) => l.trim())
  for (const line of lines) {
    const parsed = validateAssertRule(line.trim())
    rows.value.push({
      path: parsed.path || '',
      operator: parsed.operator || '',
      expected: parsed.expected || '',
      raw: line.trim(),
      error: parsed.error,
    })
  }
}

function handleConfirm() {
  // Re-validate all
  for (let i = 0; i < rows.value.length; i++) {
    validateRow(i)
  }
  const validRules = rows.value
    .filter((r) => r.raw.trim())
    .map((r) => r.raw.trim())
  emit('confirm', validRules)
}
</script>

<template>
  <a-modal
    :open="visible"
    :title="t('assertRules.modal.title')"
    width="850px"
    @ok="handleConfirm"
    @cancel="emit('cancel')"
  >
    <div class="assert-rules-modal">
      <div class="rules-toolbar">
        <a-button size="small" type="primary" @click="addRule">
          + {{ t('assertRules.addRule') }}
        </a-button>
        <a-button size="small" @click="batchPaste">
          {{ t('assertRules.batchPaste') }}
        </a-button>
      </div>

      <div v-if="rows.length === 0" class="rules-empty">
        {{ t('assertRules.empty') }}
      </div>

      <div v-for="(row, i) in rows" :key="i" class="rule-row">
        <div class="rule-index">{{ i + 1 }}</div>
        <div class="rule-fields">
          <a-form-item
            :label="t('assertRules.modal.path')"
            class="rule-form-item"
            :validate-status="row.error ? 'error' : ''"
          >
            <a-input
              :value="row.path"
              size="small"
              :placeholder="t('assertRules.modal.pathPlaceholder')"
              @change="(e: any) => onPathChange(i, e.target.value)"
            />
          </a-form-item>
          <a-form-item
            :label="t('assertRules.modal.operator')"
            class="rule-form-item rule-operator"
          >
            <a-select
              :value="row.operator"
              size="small"
              @change="(v: string) => onOperatorChange(i, v)"
            >
              <a-select-option
                v-for="op in OPERATORS"
                :key="op.value"
                :value="op.value"
              >
                {{ op.label }}
              </a-select-option>
            </a-select>
          </a-form-item>
          <a-form-item
            v-if="OPERATORS.find((o) => o.value === row.operator)?.needsExpected !== false"
            :label="t('assertRules.modal.expected')"
            class="rule-form-item rule-expected"
          >
            <a-input
              :value="row.expected"
              size="small"
              :placeholder="t('assertRules.modal.expectedPlaceholder')"
              @change="(e: any) => onExpectedChange(i, e.target.value)"
            />
          </a-form-item>
          <a-tooltip v-if="row.error" :title="row.error">
            <span class="rule-error-icon">!</span>
          </a-tooltip>
        </div>
        <a-button size="small" type="text" danger @click="removeRule(i)">&times;</a-button>
      </div>
    </div>
  </a-modal>
</template>

<style scoped>
.assert-rules-modal {
  max-height: 450px;
  overflow-y: auto;
}

.rules-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.rules-empty {
  padding: 24px;
  text-align: center;
  color: #bbb;
  font-size: 13px;
}

.rule-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 0;
  border-bottom: 1px solid #f0f0f0;
}

.rule-index {
  width: 24px;
  height: 28px;
  line-height: 28px;
  text-align: center;
  font-size: 12px;
  color: #999;
  background: #f5f5f5;
  border-radius: 4px;
  flex-shrink: 0;
  margin-top: 4px;
}

.rule-fields {
  flex: 1;
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.rule-form-item {
  margin-bottom: 0;
  min-width: 120px;
}

.rule-form-item :deep(.ant-form-item-label) {
  padding-bottom: 0;
}

.rule-form-item :deep(.ant-form-item-label > label) {
  font-size: 11px;
  height: auto;
}

.rule-operator {
  width: 140px;
}

.rule-expected {
  flex: 1;
  min-width: 140px;
}

.rule-error-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #ff4d4f;
  color: #fff;
  font-size: 11px;
  font-weight: bold;
  flex-shrink: 0;
  cursor: help;
}
</style>
