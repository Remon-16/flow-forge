<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { validateAssertRule } from '../../utils/assert-rules-validator'
import type { AssertRuleParsed } from '../../utils/assert-rules-validator'

const { t } = useI18n()

const props = defineProps<{
  modelValue: string[] | null
  disabled?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: string[] | null): void
}>()

// Internal state: array of rule strings
const rules = ref<string[]>(props.modelValue ? [...props.modelValue] : [])

// Validation results, indexed by position
const validationResults = ref<Map<number, AssertRuleParsed>>(new Map())

// Sync from external changes
watch(
  () => props.modelValue,
  (val) => {
    rules.value = val ? [...val] : []
    revalidateAll()
  },
)

function emitChange() {
  const cleaned = rules.value.map((r) => r.trim()).filter((r) => r !== '')
  emit('update:modelValue', cleaned.length > 0 ? cleaned : null)
}

function revalidateAll() {
  const map = new Map<number, AssertRuleParsed>()
  rules.value.forEach((rule, i) => {
    if (rule.trim()) {
      map.set(i, validateAssertRule(rule))
    }
  })
  validationResults.value = map
}

function onRuleInput(index: number, value: string) {
  rules.value[index] = value
  if (value.trim()) {
    validationResults.value.set(index, validateAssertRule(value))
  } else {
    validationResults.value.delete(index)
  }
  emitChange()
}

function addRule() {
  rules.value.push('')
}

function removeRule(index: number) {
  rules.value.splice(index, 1)
  validationResults.value.delete(index)
  emitChange()
}

function handleBatchPaste() {
  const text = prompt(t('assertRules.batchPasteHint'))
  if (!text) return

  const lines = text
    .split('\n')
    .map((l) => l.trim())
    .filter((l) => l !== '')

  for (const line of lines) {
    rules.value.push(line)
  }
  revalidateAll()
  emitChange()
}

const hasRules = computed(() => rules.value.length > 0)
</script>

<template>
  <div class="assert-rules-editor">
    <div v-if="!hasRules" class="rules-empty">
      <span class="empty-text">{{ t('assertRules.empty') }}</span>
    </div>

    <div v-else class="rules-list">
      <div
        v-for="(rule, index) in rules"
        :key="index"
        class="rule-row"
      >
        <a-input
          :value="rule"
          :placeholder="t('assertRules.rulePlaceholder')"
          :disabled="disabled"
          size="small"
          @update:value="(val: string) => onRuleInput(index, val)"
        />
        <a-tooltip
          v-if="validationResults.get(index)?.error"
          :title="validationResults.get(index)!.error!"
          placement="top"
        >
          <span class="rule-status error">
            <span class="status-icon">&#10007;</span>
          </span>
        </a-tooltip>
        <span
          v-else-if="rule.trim() && validationResults.get(index)"
          class="rule-status success"
        >
          <span class="status-icon">&#10003;</span>
        </span>
        <a-button
          type="text"
          size="small"
          danger
          :disabled="disabled"
          @click="removeRule(index)"
        >
          &times;
        </a-button>
      </div>
    </div>

    <div v-if="!disabled" class="rules-actions">
      <a-button size="small" type="dashed" @click="addRule">
        + {{ t('assertRules.addRule') }}
      </a-button>
      <a-button size="small" type="dashed" @click="handleBatchPaste">
        {{ t('assertRules.batchPaste') }}
      </a-button>
    </div>
  </div>
</template>

<style scoped>
.assert-rules-editor {
  min-width: 200px;
}

.rules-empty {
  padding: 4px 0;
}

.empty-text {
  color: #bbb;
  font-size: 12px;
  font-style: italic;
}

.rules-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 6px;
}

.rule-row {
  display: flex;
  align-items: center;
  gap: 4px;
}

.rule-row :deep(.ant-input) {
  flex: 1;
}

.rule-status {
  font-size: 14px;
  width: 18px;
  text-align: center;
  flex-shrink: 0;
}

.rule-status.success .status-icon {
  color: #52c41a;
}

.rule-status.error .status-icon {
  color: #ff4d4f;
}

.rules-actions {
  display: flex;
  gap: 8px;
}
</style>
