<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const props = defineProps<{
  visible: boolean
  inheritData: Record<string, string>
  stepIds: string[]
}>()

const emit = defineEmits<{
  (e: 'confirm', inheritData: Record<string, string>): void
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
      const entries = Object.entries(props.inheritData || {})
      rows.value = entries.map(([key, value]) => {
        const dotIdx = value.indexOf('.')
        const stepId = dotIdx > 0 ? value.slice(0, dotIdx) : value
        const path = dotIdx > 0 ? value.slice(dotIdx + 1) : ''
        return { key, stepId, path }
      })
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
    :title="t('inheritEditor.modal.title')"
    width="750px"
    @ok="handleConfirm"
    @cancel="emit('cancel')"
  >
    <div class="inherit-editor-modal">
      <div class="inherit-toolbar">
        <a-button size="small" type="primary" @click="addVariable">
          + {{ t('inheritEditor.addVariable') }}
        </a-button>
      </div>

      <div v-if="rows.length === 0" class="inherit-empty">
        {{ t('inheritEditor.noVariables') }}
      </div>

      <div v-for="(row, i) in rows" :key="i" class="inherit-row">
        <div class="inherit-index">{{ i + 1 }}</div>
        <div class="inherit-fields">
          <a-form-item
            :label="t('inheritEditor.modal.variableName')"
            class="inherit-form-item inherit-var-name"
          >
            <a-input
              :value="row.key"
              size="small"
              :placeholder="t('inheritEditor.modal.variableNamePlaceholder')"
              @change="(e: any) => (row.key = e.target.value)"
            />
          </a-form-item>
          <a-form-item
            :label="t('inheritEditor.modal.stepId')"
            class="inherit-form-item inherit-step-id"
          >
            <a-select
              :value="row.stepId || undefined"
              size="small"
              allow-clear
              show-search
              :placeholder="t('inheritEditor.modal.stepIdPlaceholder')"
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
            :label="t('inheritEditor.modal.path')"
            class="inherit-form-item inherit-path"
          >
            <a-input
              :value="row.path"
              size="small"
              :placeholder="t('inheritEditor.modal.pathPlaceholder')"
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
.inherit-editor-modal {
  max-height: 400px;
  overflow-y: auto;
}

.inherit-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.inherit-empty {
  padding: 24px;
  text-align: center;
  color: #bbb;
  font-size: 13px;
}

.inherit-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 0;
  border-bottom: 1px solid #f0f0f0;
}

.inherit-index {
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

.inherit-fields {
  flex: 1;
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.inherit-form-item {
  margin-bottom: 0;
}

.inherit-form-item :deep(.ant-form-item-label) {
  padding-bottom: 0;
}

.inherit-form-item :deep(.ant-form-item-label > label) {
  font-size: 11px;
  height: auto;
}

.inherit-var-name {
  flex: 1;
  min-width: 120px;
}

.inherit-step-id {
  flex: 1;
  min-width: 140px;
}

.inherit-path {
  flex: 1.5;
  min-width: 160px;
}
</style>
