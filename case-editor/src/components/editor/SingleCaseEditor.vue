<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useWorkbookStore } from '../../stores/workbook'
import { SINGLE_CASE_COLUMNS, TAG_LEVELS, JSON_COLUMNS } from '../../types/excel'
import type { SingleTestCase } from '../../types/excel'
import JsonEditor from '../json-editor/JsonEditor.vue'

const { t } = useI18n()
const workbook = useWorkbookStore()

const jsonModalVisible = ref(false)
const jsonModalField = ref<string>('')
const jsonModalRow = ref<number>(-1)
const jsonValue = ref<Record<string, unknown>>({})

function openJsonEditor(index: number, field: string) {
  jsonModalRow.value = index
  jsonModalField.value = field
  jsonValue.value = (workbook.singleCases[index] as Record<string, unknown>)[field] as Record<string, unknown> || {}
  jsonModalVisible.value = true
}

function onJsonConfirm(value: Record<string, unknown>) {
  if (jsonModalRow.value >= 0 && jsonModalField.value) {
    workbook.updateSingleCaseField(jsonModalRow.value, jsonModalField.value as keyof SingleTestCase, value)
  }
  jsonModalVisible.value = false
}

function onCellChange(index: number, field: string, value: unknown) {
  workbook.updateSingleCaseField(index, field as keyof SingleTestCase, value)
}

function isJsonColumn(field: string): boolean {
  return (JSON_COLUMNS as readonly string[]).includes(field)
}

function getColumnLabel(col: string): string {
  return t(`table.${col}`)
}

// Filtered relevance options based on input
const relevanceOptions = computed(() => workbook.validTestIds)
</script>

<template>
  <div style="height: 100%; display: flex; flex-direction: column;">
    <div style="margin-bottom: 8px; display: flex; gap: 8px;">
      <a-button size="small" type="primary" @click="workbook.addSingleCase()">
        {{ t('table.addRow') }}
      </a-button>
    </div>

    <div style="flex: 1; overflow: auto;">
      <a-table
        :dataSource="workbook.singleCases"
        :pagination="false"
        size="small"
        bordered
        :scroll="{ x: 1400 }"
        rowKey="TestID"
      >
        <a-table-column
          v-for="col in SINGLE_CASE_COLUMNS"
          :key="col"
          :title="getColumnLabel(col)"
          :width="col === 'URL' || col === 'Remark' ? 200 : col === 'TestID' ? 150 : 130"
        >
          <template #default="{ record, index }">
            <!-- RelevanceID with validation -->
            <template v-if="col === 'RelevanceID'">
              <a-auto-complete
                :value="record[col]"
                :options="relevanceOptions.map((id: string) => ({ value: id }))"
                size="small"
                style="width: 100%;"
                :status="record._relevanceValid === false ? 'error' : ''"
                @change="(v: string) => onCellChange(index, col, v)"
                @select="(v: string) => onCellChange(index, col, v)"
              >
                <template v-if="record._relevanceValid === false" #suffix>
                  <a-tooltip :title="t('validator.relevanceInvalid')">
                    <span style="color: #ff4d4f;">!</span>
                  </a-tooltip>
                </template>
              </a-auto-complete>
            </template>

            <!-- JSON columns -->
            <template v-else-if="isJsonColumn(col)">
              <a-button
                size="small"
                type="link"
                style="padding: 0;"
                @click="openJsonEditor(index, col)"
              >
                {{ getColumnLabel(col) }}
                <span v-if="Object.keys(record[col] || {}).length > 0" style="color: #1677ff;">
                  ({{ Object.keys(record[col] || {}).length }})
                </span>
              </a-button>
            </template>

            <!-- Tag dropdown -->
            <template v-else-if="col === 'Tag'">
              <a-select
                :value="record[col]"
                size="small"
                style="width: 100%;"
                @change="(v: string) => onCellChange(index, col, v)"
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
                @change="(e: any) => onCellChange(index, col, e.target.value)"
              />
            </template>

            <!-- Default text input -->
            <template v-else>
              <a-input
                :value="String(record[col] ?? '')"
                size="small"
                @change="(e: any) => onCellChange(index, col, e.target.value)"
              />
            </template>
          </template>
        </a-table-column>

        <a-table-column :title="t('menu.edit')" width="80" fixed="right">
          <template #default="{ index }">
            <a-button
              size="small"
              type="link"
              danger
              @click="workbook.removeSingleCase(index)"
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
