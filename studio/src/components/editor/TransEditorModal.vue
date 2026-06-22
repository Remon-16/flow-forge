<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const props = defineProps<{
  visible: boolean
  trans: Record<string, string>
  stepIds: string[]
}>()

const emit = defineEmits<{
  (e: 'confirm', trans: Record<string, string>): void
  (e: 'cancel'): void
}>()

interface VariableRow {
  key: string
  stepId: string
  path: string
}

const rows = ref<VariableRow[]>([])

watch(
  () => props.visible,
  (v) => {
    if (v) {
      const entries = Object.entries(props.trans || {})
      rows.value = entries.map(([key, value]) => {
        const dotIdx = value.indexOf('.')
        const stepId = dotIdx > 0 ? value.slice(0, dotIdx) : value
        const path = dotIdx > 0 ? value.slice(dotIdx + 1) : ''
        return { key, stepId, path }
      })
      // Ensure at least one empty row when empty
      if (rows.value.length === 0) {
        rows.value.push({ key: '', stepId: '', path: '' })
      }
    }
  },
  { immediate: true }
)

function addVariable() {
  rows.value.push({ key: '', stepId: '', path: '' })
}

function removeVariable(index: number) {
  rows.value.splice(index, 1)
  if (rows.value.length === 0) {
    rows.value.push({ key: '', stepId: '', path: '' })
  }
}

function handleConfirm() {
  const result: Record<string, string> = {}
  for (const row of rows.value) {
    const key = row.key.trim()
    if (!key) continue
    const stepId = row.stepId.trim()
    const path = row.path.trim()
    if (!stepId || !path) continue
    result[key] = `${stepId}.${path}`
  }
  emit('confirm', result)
}
</script>

<template>
  <a-modal
    :open="visible"
    :title="t('transEditor.modal.title')"
    width="750px"
    @ok="handleConfirm"
    @cancel="emit('cancel')"
  >
    <div class="trans-editor-modal">
      <div class="trans-toolbar">
        <a-button size="small" type="primary" @click="addVariable">
          + {{ t('transEditor.addVariable') }}
        </a-button>
      </div>

      <div v-if="rows.length === 0" class="trans-empty">
        {{ t('transEditor.noVariables') }}
      </div>

      <div v-for="(row, i) in rows" :key="i" class="trans-row">
        <div class="trans-index">{{ i + 1 }}</div>
        <div class="trans-fields">
          <a-form-item
            :label="t('transEditor.modal.variableName')"
            class="trans-form-item trans-var-name"
          >
            <a-input
              :value="row.key"
              size="small"
              :placeholder="t('transEditor.modal.variableNamePlaceholder')"
              @change="(e: any) => (row.key = e.target.value)"
            />
          </a-form-item>
          <a-form-item
            :label="t('transEditor.modal.stepId')"
            class="trans-form-item trans-step-id"
          >
            <a-select
              :value="row.stepId || undefined"
              size="small"
              allow-clear
              show-search
              :placeholder="t('transEditor.modal.stepIdPlaceholder')"
              :filter-option="(input: string, option: any) =>
                (option.label || '').toLowerCase().includes(input.toLowerCase())
              "
              @change="(v: string) => (row.stepId = v || '')"
            >
              <a-select-option
                v-for="sid in stepIds"
                :key="sid"
                :value="sid"
                :label="sid"
              >
                {{ sid }}
              </a-select-option>
            </a-select>
          </a-form-item>
          <a-form-item
            :label="t('transEditor.modal.path')"
            class="trans-form-item trans-path"
          >
            <a-input
              :value="row.path"
              size="small"
              :placeholder="t('transEditor.modal.pathPlaceholder')"
              @change="(e: any) => (row.path = e.target.value)"
            />
          </a-form-item>
        </div>
        <a-button size="small" type="text" danger @click="removeVariable(i)">
          &times;
        </a-button>
      </div>
    </div>
  </a-modal>
</template>

<style scoped>
.trans-editor-modal {
  max-height: 400px;
  overflow-y: auto;
}

.trans-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.trans-empty {
  padding: 24px;
  text-align: center;
  color: #bbb;
  font-size: 13px;
}

.trans-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 0;
  border-bottom: 1px solid #f0f0f0;
}

.trans-index {
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

.trans-fields {
  flex: 1;
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.trans-form-item {
  margin-bottom: 0;
}

.trans-form-item :deep(.ant-form-item-label) {
  padding-bottom: 0;
}

.trans-form-item :deep(.ant-form-item-label > label) {
  font-size: 11px;
  height: auto;
}

.trans-var-name {
  flex: 1;
  min-width: 120px;
}

.trans-step-id {
  flex: 1;
  min-width: 140px;
}

.trans-path {
  flex: 1.5;
  min-width: 160px;
}
</style>
