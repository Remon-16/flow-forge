<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useWorkbookStore } from '../../stores/workbook'
import { API_DEF_COLUMNS, HTTP_METHODS, JSON_COLUMNS } from '../../types/excel'
import type { ApiDefinition } from '../../types/excel'
import JsonEditor from '../json-editor/JsonEditor.vue'

const { t } = useI18n()
const workbook = useWorkbookStore()

// JSON editor modal state
const jsonModalVisible = ref(false)
const jsonModalField = ref<string>('')
const jsonModalRow = ref<number>(-1)
const jsonValue = ref<Record<string, unknown>>({})

function openJsonEditor(index: number, field: string) {
  jsonModalRow.value = index
  jsonModalField.value = field
  jsonValue.value = (workbook.apiDefinitions[index] as Record<string, unknown>)[field] as Record<string, unknown> || {}
  jsonModalVisible.value = true
}

function onJsonConfirm(value: Record<string, unknown>) {
  if (jsonModalRow.value >= 0 && jsonModalField.value) {
    workbook.updateApiDefField(jsonModalRow.value, jsonModalField.value as keyof ApiDefinition, value)
  }
  jsonModalVisible.value = false
}

function onCellChange(index: number, field: string, value: unknown) {
  workbook.updateApiDefField(index, field as keyof ApiDefinition, value)
}

function isJsonColumn(field: string): boolean {
  return (JSON_COLUMNS as readonly string[]).includes(field)
}

function getColumnLabel(col: string): string {
  return t(`table.${col}`)
}
</script>

<template>
  <div style="height: 100%; display: flex; flex-direction: column;">
    <div style="margin-bottom: 8px; display: flex; gap: 8px;">
      <a-button size="small" type="primary" @click="workbook.addApiDef()">
        {{ t('table.addRow') }}
      </a-button>
    </div>

    <div style="flex: 1; overflow: auto;">
      <a-table
        :dataSource="workbook.apiDefinitions"
        :pagination="false"
        size="small"
        bordered
        :scroll="{ x: 1200 }"
        rowKey="TestID"
      >
        <a-table-column
          v-for="col in API_DEF_COLUMNS"
          :key="col"
          :title="getColumnLabel(col)"
          :width="col === 'URL' || col === 'Remark' ? 200 : col === 'TestID' || col === 'APIName' ? 150 : 100"
        >
          <template #default="{ record, index }">
            <!-- JSON columns: clickable button -->
            <template v-if="isJsonColumn(col)">
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

            <!-- Method dropdown -->
            <template v-else-if="col === 'Method'">
              <a-select
                :value="record[col]"
                size="small"
                style="width: 100%;"
                @change="(v: string) => onCellChange(index, col, v)"
              >
                <a-select-option v-for="m in HTTP_METHODS" :key="m" :value="m">
                  {{ m }}
                </a-select-option>
              </a-select>
            </template>

            <!-- StatusCode input -->
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

        <!-- Actions -->
        <a-table-column :title="t('menu.edit')" width="80" fixed="right">
          <template #default="{ index }">
            <a-button
              size="small"
              type="link"
              danger
              @click="workbook.removeApiDef(index)"
            >
              {{ t('table.deleteRow') }}
            </a-button>
          </template>
        </a-table-column>
      </a-table>
    </div>

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
