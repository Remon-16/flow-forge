<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useWorkbookStore } from '../../stores/workbook'
import { BIZ_STEP_COLUMNS, TAG_LEVELS, JSON_COLUMNS } from '../../types/excel'
import type { BizStep } from '../../types/excel'
import JsonEditor from '../json-editor/JsonEditor.vue'

const props = defineProps<{ flowIndex: number }>()

const { t } = useI18n()
const workbook = useWorkbookStore()

const jsonModalVisible = ref(false)
const jsonModalField = ref<string>('')
const jsonModalStepIdx = ref<number>(-1)
const jsonValue = ref<Record<string, unknown>>({})

const flow = computed(() => workbook.bizFlows[props.flowIndex])

// Re-run validation when flow changes
watch(
  () => props.flowIndex,
  () => {
    workbook.validateBizFlow(props.flowIndex)
  },
  { immediate: true }
)

function openJsonEditor(stepIndex: number, field: string) {
  jsonModalStepIdx.value = stepIndex
  jsonModalField.value = field
  jsonValue.value = (flow.value.steps[stepIndex] as Record<string, unknown>)[field] as Record<string, unknown> || {}
  jsonModalVisible.value = true
}

function onJsonConfirm(value: Record<string, unknown>) {
  if (jsonModalStepIdx.value >= 0 && jsonModalField.value) {
    workbook.updateBizStepField(props.flowIndex, jsonModalStepIdx.value, jsonModalField.value as keyof BizStep, value)
  }
  jsonModalVisible.value = false
}

function onCellChange(stepIndex: number, field: string, value: unknown) {
  workbook.updateBizStepField(props.flowIndex, stepIndex, field as keyof BizStep, value)
}

function isJsonColumn(field: string): boolean {
  return (JSON_COLUMNS as readonly string[]).includes(field)
}

function getColumnLabel(col: string): string {
  return t(`table.${col}`)
}

const relevanceOptions = computed(() => workbook.validTestIds)

function getRowClassName(record: BizStep) {
  if (record._stepIdDuplicate || record._relevanceValid === false || record._transError) {
    return 'row-error'
  }
  return ''
}
</script>

<template>
  <div style="height: 100%; display: flex; flex-direction: column;">
    <!-- Toolbar -->
    <div style="margin-bottom: 8px; display: flex; gap: 8px; align-items: center;">
      <span style="font-weight: 600; font-size: 14px;">
        {{ flow?.sheetName || `BizFlow ${props.flowIndex + 1}` }}
      </span>
      <a-divider type="vertical" />
      <a-button size="small" type="primary" @click="workbook.addBizStep(props.flowIndex)">
        {{ t('table.addStep') }}
      </a-button>
      <a-popconfirm
        :title="'确定删除业务链路 ' + (flow?.sheetName || '') + ' 吗？'"
        @confirm="workbook.removeBizFlow(props.flowIndex)"
      >
        <a-button size="small" danger>{{ t('table.deleteRow') }}</a-button>
      </a-popconfirm>
    </div>

    <!-- Steps table -->
    <div style="flex: 1; overflow: auto;">
      <a-table
        v-if="flow"
        :dataSource="flow.steps"
        :pagination="false"
        size="small"
        bordered
        :scroll="{ x: 1600 }"
        :rowClassName="getRowClassName"
        rowKey="StepID"
      >
        <a-table-column
          v-for="col in BIZ_STEP_COLUMNS"
          :key="col"
          :title="getColumnLabel(col)"
          :width="col === 'URL' || col === 'Remark' || col === 'Trans' ? 200 : col === 'StepID' ? 100 : 130"
        >
          <template #default="{ record, index: stepIdx }">
            <!-- StepID with duplicate check -->
            <template v-if="col === 'StepID'">
              <a-input
                :value="String(record[col] ?? '')"
                size="small"
                :status="record._stepIdDuplicate ? 'error' : ''"
                @change="(e: any) => onCellChange(stepIdx, col, e.target.value)"
              >
                <template v-if="record._stepIdDuplicate" #suffix>
                  <a-tooltip :title="t('validator.stepIdDuplicate')">
                    <span style="color: #ff4d4f;">!</span>
                  </a-tooltip>
                </template>
              </a-input>
            </template>

            <!-- RelevanceID -->
            <template v-else-if="col === 'RelevanceID'">
              <a-auto-complete
                :value="record[col]"
                :options="relevanceOptions.map((id: string) => ({ value: id }))"
                size="small"
                style="width: 100%;"
                :status="record._relevanceValid === false ? 'error' : ''"
                @change="(v: string) => onCellChange(stepIdx, col, v)"
                @select="(v: string) => onCellChange(stepIdx, col, v)"
              >
                <template v-if="record._relevanceValid === false" #suffix>
                  <a-tooltip :title="t('validator.relevanceInvalid')">
                    <span style="color: #ff4d4f;">!</span>
                  </a-tooltip>
                </template>
              </a-auto-complete>
            </template>

            <!-- Trans with validation -->
            <template v-else-if="col === 'Trans'">
              <a-tooltip :title="record._transError || ''">
                <a-input
                  :value="String(record[col] ?? '')"
                  size="small"
                  :status="record._transError ? 'error' : ''"
                  @change="(e: any) => onCellChange(stepIdx, col, e.target.value)"
                />
              </a-tooltip>
            </template>

            <!-- JSON columns -->
            <template v-else-if="isJsonColumn(col)">
              <a-button
                size="small"
                type="link"
                style="padding: 0;"
                @click="openJsonEditor(stepIdx, col)"
              >
                {{ getColumnLabel(col) }}
                <span v-if="Object.keys(record[col] || {}).length > 0" style="color: #1677ff;">
                  ({{ Object.keys(record[col] || {}).length }})
                </span>
              </a-button>
            </template>

            <!-- Tag -->
            <template v-else-if="col === 'Tag'">
              <a-select
                :value="record[col]"
                size="small"
                style="width: 100%;"
                @change="(v: string) => onCellChange(stepIdx, col, v)"
              >
                <a-select-option v-for="tag in TAG_LEVELS" :key="tag" :value="tag">
                  {{ tag }}
                </a-select-option>
              </a-select>
            </template>

            <!-- StatusCode -->
            <template v-else-if="col === 'StatusCode'">
              <a-input
                :value="String(record[col] ?? '')"
                size="small"
                @change="(e: any) => onCellChange(stepIdx, col, e.target.value)"
              />
            </template>

            <!-- Default -->
            <template v-else>
              <a-input
                :value="String(record[col] ?? '')"
                size="small"
                @change="(e: any) => onCellChange(stepIdx, col, e.target.value)"
              />
            </template>
          </template>
        </a-table-column>

        <!-- Actions -->
        <a-table-column :title="t('menu.edit')" width="120" fixed="right">
          <template #default="{ index: stepIdx }">
            <a-button
              size="small"
              type="link"
              @click="workbook.moveBizStep(props.flowIndex, stepIdx, 'up')"
              :disabled="stepIdx === 0"
            >
              {{ t('table.moveUp') }}
            </a-button>
            <a-button
              size="small"
              type="link"
              @click="workbook.moveBizStep(props.flowIndex, stepIdx, 'down')"
              :disabled="stepIdx === flow.steps.length - 1"
            >
              {{ t('table.moveDown') }}
            </a-button>
            <a-button
              size="small"
              type="link"
              danger
              @click="workbook.removeBizStep(props.flowIndex, stepIdx)"
            >
              {{ t('table.deleteRow') }}
            </a-button>
          </template>
        </a-table-column>
      </a-table>
    </div>

    <JsonEditor
      :visible="jsonModalVisible"
      :value="jsonValue"
      :title="jsonModalField"
      @confirm="onJsonConfirm"
      @cancel="jsonModalVisible = false"
    />
  </div>
</template>
