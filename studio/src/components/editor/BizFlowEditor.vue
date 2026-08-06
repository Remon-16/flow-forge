<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useWorkbookStore } from '../../stores/workbook'
import { useSettingsStore } from '../../stores/settings'
import { BIZ_STEP_COLUMNS, TAG_LEVELS, JSON_COLUMNS } from '../../types/excel'
import type { BizStep } from '../../types/excel'
import JsonEditor from '../json-editor/JsonEditor.vue'
import AssertRulesModal from './AssertRulesModal.vue'
import InheritEditorModal from './InheritEditorModal.vue'
import { normalizeJsonValue } from '../../utils/json-helper'

const props = defineProps<{ flowIndex: number; searchBarVisible?: boolean }>()

const { t } = useI18n()
const workbook = useWorkbookStore()
const settings = useSettingsStore()

const jsonModalVisible = ref(false)
const jsonModalField = ref<string>('')
const jsonModalStepIdx = ref<number>(-1)
const jsonValue = ref<Record<string, unknown>>({})

const flow = computed(() => workbook.bizFlows[props.flowIndex])

const scrollY = computed(() => {
  const base = 200
  const searchBar = props.searchBarVisible ? 85 : 0
  return `calc(100vh - ${base + searchBar}px)`
})

const scrollX = computed(() => Math.ceil(2400 / settings.zoom))

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
  const raw = (flow.value.steps[stepIndex] as Record<string, unknown>)[field]
  jsonValue.value = normalizeJsonValue(raw)
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

// AssertRules modal state
const assertRulesModalVisible = ref(false)
const assertRulesModalStepIdx = ref(-1)
const assertRulesValue = ref<string[] | null>(null)

function openAssertRulesEditor(stepIndex: number) {
  assertRulesModalStepIdx.value = stepIndex
  assertRulesValue.value = flow.value.steps[stepIndex].AssertRules as string[] | null
  assertRulesModalVisible.value = true
}

function onAssertRulesConfirm(rules: string[]) {
  if (assertRulesModalStepIdx.value >= 0) {
    workbook.updateBizStepField(props.flowIndex, assertRulesModalStepIdx.value, 'AssertRules', rules.length > 0 ? rules : null)
  }
  assertRulesModalVisible.value = false
}

function formatRules(val: string[] | null): string {
  if (!val || val.length === 0) return ''
  return val.join('\n')
}

// Inherit editing
const stepIds = computed(() => flow.value?.steps.map(s => s.StepID).filter(Boolean) || [])

function parseInheritValue(raw: unknown): Record<string, string> {
  if (!raw) return {}
  if (typeof raw === 'object' && !Array.isArray(raw)) return raw as Record<string, string>
  if (typeof raw === 'string') {
    const trimmed = raw.trim()
    if (!trimmed) return {}
    try {
      const parsed = JSON.parse(trimmed)
      if (typeof parsed === 'object' && !Array.isArray(parsed)) return parsed as Record<string, string>
    } catch {
      // Old format fallback
      const result: Record<string, string> = {}
      const pairs = trimmed.split(',').map(p => p.trim()).filter(Boolean)
      for (const pair of pairs) {
        const eqIdx = pair.indexOf('=')
        if (eqIdx < 0) continue
        result[pair.slice(0, eqIdx).trim()] = pair.slice(eqIdx + 1).trim()
      }
      return result
    }
  }
  return {}
}

const inheritModalVisible = ref(false)
const inheritModalStepIdx = ref(-1)
const inheritModalValue = ref<Record<string, string>>({})

function openInheritEditor(stepIdx: number) {
  inheritModalStepIdx.value = stepIdx
  inheritModalValue.value = parseInheritValue(flow.value.steps[stepIdx].Inherit)
  inheritModalVisible.value = true
}

function onInheritConfirm(value: Record<string, string>) {
  if (inheritModalStepIdx.value >= 0) {
    onCellChange(inheritModalStepIdx.value, 'Inherit', JSON.stringify(value))
  }
  inheritModalVisible.value = false
}

function formatInheritDisplay(val: unknown): string {
  if (!val) return ''
  if (typeof val === 'string') {
    // Try to parse then pretty-print
    try {
      const parsed = JSON.parse(val)
      if (parsed && typeof parsed === 'object') return JSON.stringify(parsed, null, 2)
    } catch { /* ignore */ }
    return val
  }
  return JSON.stringify(val, null, 2)
}

// Inline Inherit editing cache
const inheritEditCache = ref<Record<string, string>>({})

function getInheritEditText(rowIdx: number, raw: unknown): string {
  const key = `inherit_${rowIdx}`
  if (key in inheritEditCache.value) return inheritEditCache.value[key]
  return formatInheritDisplay(raw)
}

function onInheritEditChange(rowIdx: number, text: string) {
  inheritEditCache.value[`inherit_${rowIdx}`] = text
}

function onInheritEditBlur(rowIdx: number) {
  const cacheKey = `inherit_${rowIdx}`
  // 未触发 change（仅点击/失焦）则保持原值 / No change event fired (click only, no edit): keep original value
  if (!(cacheKey in inheritEditCache.value)) return
  const text = (inheritEditCache.value[cacheKey] || '').trim()
  if (!text) {
    onCellChange(rowIdx, 'Inherit', '{}')
    delete inheritEditCache.value[cacheKey]
    return
  }
  try {
    const parsed = JSON.parse(text)
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      onCellChange(rowIdx, 'Inherit', JSON.stringify(parsed))
      delete inheritEditCache.value[cacheKey]
    }
  } catch {
    // Keep dirty text; validation will show error
  }
}

const relevanceOptions = computed(() => workbook.validTestIdOptions)

function getRowClassName(record: BizStep) {
  if ((record as any)._searchActive) return 'row-search-active'
  if ((record as any)._searchMatch) return 'row-search-match'
  if (record._stepIdDuplicate
      || record._inheritError || (record as any)._urlWarning) {
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
    <div style="flex: 1; min-height: 0;">
      <a-table
        v-if="flow"
        :dataSource="flow.steps"
        :pagination="false"
        size="small"
        bordered
        :scroll="{ x: scrollX, y: scrollY }"
        :rowClassName="getRowClassName"
        :rowKey="(r: any) => r._uid"
      >
        <a-table-column
          v-for="col in BIZ_STEP_COLUMNS"
          :key="col"
          :title="getColumnLabel(col)"
          :width="isJsonColumn(col) ? 250 : col === 'AssertRules' ? 280 : col === 'URL' || col === 'Remark' || col === 'Inherit' ? 200 : col === 'StepID' ? 100 : 130"
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
                :options="relevanceOptions"
                size="small"
                style="width: 100%;"
                :dropdown-match-select-width="false"
                :dropdown-style="{ minWidth: '400px' }"
                :filter-option="(inputValue: string, option: any) => {
                  const label = (option.label || '').toLowerCase()
                  const val = (option.value || '').toLowerCase()
                  const q = inputValue.toLowerCase()
                  return label.includes(q) || val.includes(q)
                }"
                @change="(v: string) => onCellChange(stepIdx, col, v)"
                @select="(v: string) => onCellChange(stepIdx, col, v)"
              >
              </a-auto-complete>
            </template>

            <!-- Inherit with validation -->
            <template v-else-if="col === 'Inherit'">
              <div style="display: flex; flex-direction: column; gap: 2px; min-width: 200px;">
                <a-button
                  size="small"
                  type="link"
                  style="padding: 0; text-align: left; height: auto; font-size: 12px;"
                  @click="openInheritEditor(stepIdx)"
                >
                  {{ t('inheritEditor.editDetails') }}: {{ getColumnLabel(col) }}
                </a-button>
                <a-textarea
                  :value="getInheritEditText(stepIdx, record[col])"
                  :autoSize="{ minRows: 2, maxRows: 6 }"
                  size="small"
                  style="font-family: monospace; font-size: 12px;"
                  :status="record._inheritError ? 'error' : ''"
                  @change="(e: any) => onInheritEditChange(stepIdx, e.target.value)"
                  @blur="() => onInheritEditBlur(stepIdx)"
                />
                <span v-if="record._inheritError" style="color: #ff4d4f; font-size: 11px;">
                  &#x2715; {{ record._inheritError }}
                </span>
              </div>
            </template>

            <!-- JSON columns: details link + editable textarea -->
            <template v-else-if="isJsonColumn(col)">
              <div style="display: flex; flex-direction: column; gap: 2px; min-width: 200px;">
                <a-button
                  size="small"
                  type="link"
                  style="padding: 0; text-align: left; height: auto; font-size: 12px;"
                  @click="openJsonEditor(stepIdx, col)"
                >
                  {{ t('jsonEditor.details') }}: {{ getColumnLabel(col) }}
                </a-button>
                <a-textarea
                  :value="getJsonEditText(stepIdx, col, record[col])"
                  :autoSize="{ minRows: 3, maxRows: 8 }"
                  size="small"
                  style="font-family: monospace; font-size: 12px;"
                  @change="(e: any) => onJsonEditChange(stepIdx, col, e.target.value)"
                  @blur="() => onJsonEditBlur(stepIdx, col)"
                />
                <span v-if="isJsonInvalid(stepIdx, col)" style="color: #ff4d4f; font-size: 11px;">
                  ✕ {{ t('jsonEditor.parseError') }}
                </span>
              </div>
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

            <!-- AssertRules: edit details button + textarea -->
            <template v-else-if="col === 'AssertRules'">
              <div style="display: flex; flex-direction: column; gap: 2px; min-width: 200px;">
                <a-button
                  size="small"
                  type="link"
                  style="padding: 0; text-align: left; height: auto; font-size: 12px;"
                  @click="openAssertRulesEditor(stepIdx)"
                >
                  {{ t('assertRules.editDetails') }}
                </a-button>
                <a-textarea
                  :value="formatRules(record[col] as string[] | null)"
                  :autoSize="{ minRows: 3, maxRows: 8 }"
                  size="small"
                  style="font-family: monospace; font-size: 12px;"
                  :placeholder="t('assertRules.empty')"
                />
              </div>
            </template>

            <!-- Remark: textarea -->
            <template v-else-if="col === 'Remark'">
              <a-textarea
                :value="String(record[col] ?? '')"
                :autoSize="{ minRows: 2, maxRows: 6 }"
                size="small"
                @change="(e: any) => onCellChange(stepIdx, col, e.target.value)"
              />
            </template>

            <!-- URL with warning -->
            <template v-else-if="col === 'URL'">
              <a-input
                :value="String(record[col] ?? '')"
                size="small"
                :status="String(record[col] ?? '').includes('<URL not exist>') ? 'error' : ''"
                @change="(e: any) => onCellChange(stepIdx, col, e.target.value)"
              >
                <template v-if="String(record[col] ?? '').includes('<URL not exist>')" #suffix>
                  <a-tooltip :title="t('validator.urlWarning')">
                    <span style="color: #ff4d4f; font-weight: bold;">&#10007;</span>
                  </a-tooltip>
                </template>
              </a-input>
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

    <!-- AssertRules Modal -->
    <AssertRulesModal
      :visible="assertRulesModalVisible"
      :rules="assertRulesValue"
      @confirm="onAssertRulesConfirm"
      @cancel="assertRulesModalVisible = false"
    />

    <!-- Inherit Editor Modal -->
    <InheritEditorModal
      :visible="inheritModalVisible"
      :inheritData="inheritModalValue"
      :stepIds="stepIds"
      @confirm="onInheritConfirm"
      @cancel="inheritModalVisible = false"
    />
  </div>
</template>

<style scoped>
:deep(.ant-table-header) {
  overflow-y: scroll !important;
}
:deep(.ant-table-header::-webkit-scrollbar) {
  display: none;
}
:deep(.row-search-match td) {
  background: #fff7cc !important;
}
:deep(.row-search-active td) {
  background: #ffd54f !important;
}
</style>
