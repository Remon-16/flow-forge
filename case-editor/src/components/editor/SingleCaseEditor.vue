<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useWorkbookStore } from '../../stores/workbook'
import { SINGLE_CASE_COLUMNS, TAG_LEVELS, JSON_COLUMNS } from '../../types/excel'
import type { SingleTestCase } from '../../types/excel'
import JsonEditor from '../json-editor/JsonEditor.vue'
import { normalizeJsonValue } from '../../utils/json-helper'

const { t } = useI18n()
const workbook = useWorkbookStore()

const jsonModalVisible = ref(false)
const jsonModalField = ref<string>('')
const jsonModalRow = ref<number>(-1)
const jsonValue = ref<Record<string, unknown>>({})

function openJsonEditor(index: number, field: string) {
  jsonModalRow.value = index
  jsonModalField.value = field
  const raw = (workbook.singleCases[index] as Record<string, unknown>)[field]
  jsonValue.value = normalizeJsonValue(raw)
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

function formatJsonDisplay(val: unknown): string {
  if (val === null || val === undefined) return ''
  if (typeof val === 'string') return val
  return JSON.stringify(val, null, 2)
}

// Inline JSON editing state per cell
const jsonEditCache = ref<Record<string, string>>({})

function getJsonEditText(rowIdx: number, col: string, raw: unknown): string {
  const key = `${rowIdx}_${col}`
  if (key in jsonEditCache.value) return jsonEditCache.value[key]
  return formatJsonDisplay(raw)
}

function onJsonEditChange(rowIdx: number, col: string, text: string) {
  jsonEditCache.value[`${rowIdx}_${col}`] = text
}

function onJsonEditBlur(rowIdx: number, col: string) {
  const key = `${rowIdx}_${col}`
  const text = jsonEditCache.value[key]
  if (!text) return
  try {
    const parsed = JSON.parse(text)
    if (parsed && typeof parsed === 'object') {
      onCellChange(rowIdx, col, parsed)
      delete jsonEditCache.value[key]
    }
  } catch {
    // keep dirty text for display; validation will show indicator
  }
}

function isJsonInvalid(rowIdx: number, col: string): boolean {
  const text = jsonEditCache.value[`${rowIdx}_${col}`]
  if (!text || !text.trim()) return false
  const trimmed = text.trim()
  if (!trimmed.startsWith('{') && !trimmed.startsWith('[')) return false
  try {
    JSON.parse(trimmed)
    return false
  } catch {
    return true
  }
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
        :rowKey="(r: any) => r._uid"
      >
        <a-table-column
          v-for="col in SINGLE_CASE_COLUMNS"
          :key="col"
          :title="getColumnLabel(col)"
          :width="isJsonColumn(col) ? 250 : col === 'URL' || col === 'Remark' ? 200 : col === 'TestID' ? 150 : 130"
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

            <!-- JSON columns: details link + editable textarea -->
            <template v-else-if="isJsonColumn(col)">
              <div style="display: flex; flex-direction: column; gap: 2px; min-width: 200px;">
                <a-button
                  size="small"
                  type="link"
                  style="padding: 0; text-align: left; height: auto; font-size: 12px;"
                  @click="openJsonEditor(index, col)"
                >
                  {{ t('jsonEditor.details') }}: {{ getColumnLabel(col) }}
                </a-button>
                <a-textarea
                  :value="getJsonEditText(index, col, record[col])"
                  :autoSize="{ minRows: 3, maxRows: 8 }"
                  size="small"
                  style="font-family: monospace; font-size: 12px;"
                  @change="(e: any) => onJsonEditChange(index, col, e.target.value)"
                  @blur="() => onJsonEditBlur(index, col)"
                />
                <span v-if="isJsonInvalid(index, col)" style="color: #ff4d4f; font-size: 11px;">
                  ✕ {{ t('jsonEditor.parseError') }}
                </span>
              </div>
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
