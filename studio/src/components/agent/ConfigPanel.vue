<script setup lang="ts">
// ConfigPanel — 动态配置节编辑器。根据实际 configData 渲染所有键值，取代预定义字段列表。
// Dynamic config section editor. Renders all keys from actual configData, replacing predefined field lists.
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  ArrowUpOutlined,
  ArrowDownOutlined,
} from '@ant-design/icons-vue'
import JsonEditor from '../json-editor/JsonEditor.vue'
import { normalizeJsonValue } from '../../utils/json-helper'
import { snakeToCamel } from '../../utils/string-utils'

const { t } = useI18n()

const props = defineProps<{
  configData: Record<string, any>
  /** 使用内联编辑（非 JsonEditor）的 section key 列表 / Section keys using inline editing (no JsonEditor) */
  inlineArraySections?: string[]
  /** 内联 section 中应作为对象数组的字段路径（如 skills.agents）/ Fields within inline sections that are object arrays (e.g. skills.agents)
   *   当数组为空时，通过此列表确定应使用对象数组模板还是字符串数组模板。
   *   When an array is empty, this list determines whether to use the object array or string array template. */
  objectArrayFields?: string[]
}>()

const emit = defineEmits<{
  change: [key: string, value: any]
}>()

// 默认折叠 / Collapsed by default
const activeKeys = ref<string[]>([])

// JSON 编辑器模态框状态 / JSON editor modal state
const showJsonEditor = ref(false)
const editingSectionKey = ref('')
const editingFieldKey = ref('')
const editingFieldValue = ref<Record<string, unknown>>({})

// 配置节定义（仅 key + 标签，字段从实际数据动态渲染）
// Section definitions (key + label only; fields rendered dynamically from actual data)
const sections = computed(() => [
  { key: 'pipeline', label: t('agent.config_pipeline') },
  { key: 'validation', label: t('agent.config_validation') },
  { key: 'plugins', label: t('agent.config_plugins') },
  { key: 'skills', label: t('agent.config_skills') },
  { key: 'logging', label: t('agent.config_logging') },
])

// 从 configData 获取某 section 的实际数据 / Get actual data for a section from configData
function getSectionData(sectionKey: string): Record<string, unknown> {
  const sec = props.configData?.[sectionKey]
  if (sec && typeof sec === 'object' && !Array.isArray(sec)) {
    return sec as Record<string, unknown>
  }
  return {}
}

// 类型判断 / Type guards
function isScalar(v: unknown): v is string | number {
  return typeof v === 'string' || typeof v === 'number'
}
function isBool(v: unknown): v is boolean {
  return typeof v === 'boolean'
}
function isNestedObject(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v)
}

// 发送变更事件 / Emit change event
function emitChange(sectionKey: string, fieldKey: string, val: unknown) {
  emit('change', `${sectionKey}.${fieldKey}`, val)
}

// 判断数字类型（用于 number input）/ Check if numeric (for number input)
function isNumeric(v: unknown): v is number {
  return typeof v === 'number'
}

// 格式化非标量值为只读文本 / Format non-scalar value as readonly text
function formatReadonly(v: unknown): string {
  if (Array.isArray(v)) return JSON.stringify(v)
  return String(v)
}

/**
 * 根据 YAML 配置键查找 i18n 翻译标签，未找到则回退到原始键名。
 * Look up i18n translation label by YAML config key; fall back to raw key if not found.
 * YAML 键为 snake_case，i18n 键为 agent.config_ + camelCase。
 * YAML keys are snake_case; i18n keys are agent.config_ + camelCase.
 */
function labelFor(key: string | number): string {
  const keyStr = String(key)
  const camelKey = snakeToCamel(keyStr)
  const i18nKey = 'agent.config_' + camelKey
  const translated = t(i18nKey)
  // t() 在未找到翻译时返回键名本身 / t() returns the key itself when translation is missing
  return translated !== i18nKey ? translated : keyStr
}

/** 判断某个 section 是否使用内联数组编辑 / Check if section uses inline array editing */
function isInlineSection(sectionKey: string): boolean {
  return props.inlineArraySections?.includes(sectionKey) ?? false
}

/** 判断内联 section 中的某个字段是否为对象数组（显式声明）/ Check if a field in an inline section is explicitly an object array */
function isObjectArrayField(sectionKey: string, fieldKey: string): boolean {
  return props.objectArrayFields?.includes(`${sectionKey}.${fieldKey}`) ?? false
}

/** 通过路径从 configData 获取值 / Get value from configData by dot-separated path */
function getValueAtPath(path: string): unknown {
  const parts = path.split('.')
  let current: any = props.configData
  for (const part of parts) {
    if (current && typeof current === 'object') current = current[part]
    else return undefined
  }
  return current
}

/** 更新数组中的某一项 / Update an item in an array */
function updateArrayItem(sectionKey: string, fieldPath: string, index: number, newValue: unknown) {
  const arr = getValueAtPath(`${sectionKey}.${fieldPath}`)
  if (!Array.isArray(arr)) return
  const newArr = [...arr]
  newArr[index] = newValue
  emitChange(sectionKey, fieldPath, newArr)
}

/** 更新对象数组中某项的某个字段 / Update a field in an object array item */
function updateArrayItemField(sectionKey: string, fieldPath: string, index: number, fieldKey: string, value: unknown) {
  const arr = getValueAtPath(`${sectionKey}.${fieldPath}`)
  if (!Array.isArray(arr)) return
  const newArr = [...arr]
  const item = { ...(newArr[index] as Record<string, unknown>) }
  item[fieldKey] = value
  newArr[index] = item
  emitChange(sectionKey, fieldPath, newArr)
}

/** 删除数组中的某一项 / Delete an item from an array */
function deleteArrayItem(sectionKey: string, fieldPath: string, index: number) {
  const arr = getValueAtPath(`${sectionKey}.${fieldPath}`)
  if (!Array.isArray(arr)) return
  const newArr = [...arr]
  newArr.splice(index, 1)
  emitChange(sectionKey, fieldPath, newArr)
}

/** 移动数组中的某一项（上移/下移）/ Move an array item up or down */
function moveArrayItem(sectionKey: string, fieldPath: string, index: number, delta: number) {
  const arr = getValueAtPath(`${sectionKey}.${fieldPath}`)
  if (!Array.isArray(arr)) return
  const targetIdx = index + delta
  if (targetIdx < 0 || targetIdx >= arr.length) return
  const newArr = [...arr]
  // 交换两项 / Swap two items
  const tmp = newArr[index]
  newArr[index] = newArr[targetIdx]
  newArr[targetIdx] = tmp
  emitChange(sectionKey, fieldPath, newArr)
}

/** 向数组末尾添加一项 / Add an item to the end of an array */
function addArrayItem(sectionKey: string, fieldPath: string, defaultItem: unknown) {
  const arr = getValueAtPath(`${sectionKey}.${fieldPath}`)
  const base = Array.isArray(arr) ? [...arr] : []
  base.push(defaultItem)
  emitChange(sectionKey, fieldPath, base)
}

/**
 * 打开 JSON 编辑器模态框编辑复杂值（数组/深层对象）。
 * Open JSON editor modal to edit complex values (arrays/deep objects).
 * 数组值用字段名包裹为对象（JsonEditor 期望 Record 类型）。
 * Arrays are wrapped with field key as property (JsonEditor expects Record).
 */
function openFieldJsonEditor(sectionKey: string, fieldKey: string, val: unknown) {
  editingSectionKey.value = sectionKey
  editingFieldKey.value = fieldKey
  if (Array.isArray(val)) {
    editingFieldValue.value = { [fieldKey]: val }
  } else {
    editingFieldValue.value = normalizeJsonValue(val)
  }
  showJsonEditor.value = true
}

/**
 * JSON 编辑器确认回调：还原包裹的数组并 emit 变更。
 * JSON editor confirm: unwrap arrays and emit change.
 */
function onFieldJsonConfirm(value: Record<string, unknown>) {
  const keys = Object.keys(value)
  // 如果仅有一个键且与字段名匹配 → 还原包裹的数组 / Single key matches field → unwrap array
  if (keys.length === 1 && keys[0] === editingFieldKey.value) {
    emitChange(editingSectionKey.value, editingFieldKey.value, value[editingFieldKey.value])
  } else {
    emitChange(editingSectionKey.value, editingFieldKey.value, value)
  }
  showJsonEditor.value = false
}
</script>

<template>
  <div class="config-panel">
    <a-collapse v-model:activeKey="activeKeys" :bordered="false">
      <a-collapse-panel
        v-for="sec in sections"
        :key="sec.key"
        :header="sec.label"
      >
        <!-- 无数据提示 / Empty hint -->
        <div
          v-if="Object.keys(getSectionData(sec.key)).length === 0"
          style="color: #999; font-size: 12px;"
        >
          {{ t('agent.config_emptyHint') }}
        </div>

        <!-- 动态渲染所有键 / Dynamically render all keys -->
        <template v-for="(val, key) in getSectionData(sec.key)" :key="String(key)">
          <!-- 标量/字符串：输入框 / Scalar/string: input -->
          <div v-if="isScalar(val)" class="config-field">
            <label>{{ labelFor(key) }}</label>
            <a-input-number
              v-if="isNumeric(val)"
              :value="val"
              size="small"
              style="width: 100%"
              @change="(v: any) => emitChange(sec.key, key, v)"
            />
            <a-input
              v-else
              :value="String(val)"
              size="small"
              @change="(e: Event) => {
                const target = (e.target as HTMLInputElement)
                emitChange(sec.key, key, target.value)
              }"
            />
          </div>

          <!-- 布尔：开关 / Boolean: switch -->
          <div v-else-if="isBool(val)" class="config-field">
            <label>{{ labelFor(key) }}</label>
            <a-switch
              :checked="val"
              size="small"
              @change="(v: boolean) => emitChange(sec.key, key, v)"
            />
          </div>

          <!-- 嵌套对象：展开子属性 / Nested object: expand sub-properties -->
          <div v-else-if="isNestedObject(val)" class="config-group">
            <span class="config-group-label">{{ labelFor(key) }}</span>
            <template v-for="(subVal, subKey) in val" :key="String(subKey)">
              <div v-if="isScalar(subVal)" class="config-field indent-field">
                <label>{{ labelFor(subKey) }}</label>
                <a-input-number
                  v-if="isNumeric(subVal)"
                  :value="subVal"
                  size="small"
                  style="width: 100%"
                  @change="(v: any) => emitChange(sec.key, key + '.' + subKey, v)"
                />
                <a-input
                  v-else
                  :value="String(subVal)"
                  size="small"
                  @change="(e: Event) => {
                    const target = (e.target as HTMLInputElement)
                    emitChange(sec.key, key + '.' + subKey, target.value)
                  }"
                />
              </div>
              <!-- 二级嵌套对象：递归展开 / Second-level nested: recurse -->
              <div v-else-if="isNestedObject(subVal)" class="config-group indent-group">
                <span class="config-group-label">{{ labelFor(subKey) }}</span>
                <div
                  v-for="(subSubVal, subSubKey) in subVal"
                  :key="String(subSubKey)"
                  class="config-field indent-field-2"
                >
                  <label>{{ labelFor(subSubKey) }}</label>
                  <a-input
                    v-if="isScalar(subSubVal)"
                    :value="String(subSubVal)"
                    size="small"
                    @change="(e: Event) => {
                      const target = (e.target as HTMLInputElement)
                      emitChange(sec.key, key + '.' + subKey + '.' + subSubKey, target.value)
                    }"
                  />
                  <a-switch
                    v-else-if="isBool(subSubVal)"
                    :checked="subSubVal"
                    size="small"
                    @change="(v: boolean) => emitChange(sec.key, key + '.' + subKey + '.' + subSubKey, v)"
                  />
                  <!-- 内联 section 二级嵌套对象展开 / Inline section depth-2 nested object expand -->
                  <div v-else-if="isInlineSection(sec.key) && isNestedObject(subSubVal)" class="config-group" style="margin-left: 6px;">
                    <span class="config-group-label">{{ labelFor(subSubKey) }}</span>
                    <div v-for="(deepVal, deepKey) in subSubVal" :key="String(deepKey)" class="config-field indent-field-2">
                      <label>{{ labelFor(deepKey) }}</label>
                      <a-input
                        v-if="typeof deepVal === 'string' || typeof deepVal === 'number'"
                        :value="String(deepVal)"
                        size="small"
                        @change="(e: Event) => {
                          const target = (e.target as HTMLInputElement)
                          emitChange(sec.key, key + '.' + subKey + '.' + subSubKey + '.' + deepKey, target.value)
                        }"
                      />
                      <a-switch
                        v-else-if="typeof deepVal === 'boolean'"
                        :checked="deepVal"
                        size="small"
                        @change="(v: boolean) => emitChange(sec.key, key + '.' + subKey + '.' + subSubKey + '.' + deepKey, v)"
                      />
                      <span v-else class="config-readonly">{{ formatReadonly(deepVal) }}</span>
                    </div>
                  </div>
                  <!-- 非内联 section：只读 + JsonEditor / Non-inline: readonly + JsonEditor -->
                  <div v-else style="display: flex; align-items: center; gap: 4px;">
                    <span class="config-readonly" style="flex: 1;">{{ formatReadonly(subSubVal) }}</span>
                    <a-button size="small" type="link" @click="openFieldJsonEditor(sec.key, String(key) + '.' + String(subKey), subSubVal)">
                      {{ t('jsonEditor.editDetails') }}
                    </a-button>
                  </div>
                </div>
              </div>
              <div v-else-if="isBool(subVal)" class="config-field indent-field">
                <label>{{ labelFor(subKey) }}</label>
                <a-switch
                  :checked="subVal"
                  size="small"
                  @change="(v: boolean) => emitChange(sec.key, key + '.' + subKey, v)"
                />
              </div>
              <!-- 内联 section 字符串数组 / Inline section string array -->
              <div v-else-if="isInlineSection(sec.key) && Array.isArray(subVal) && !isObjectArrayField(sec.key, String(key) + '.' + String(subKey)) && (subVal.length === 0 || typeof subVal[0] === 'string' || typeof subVal[0] === 'number')" class="config-array indent-field">
                <label>{{ labelFor(subKey) }}</label>
                <div v-for="(item, idx) in subVal" :key="idx" class="array-item-row">
                  <a-input :value="String(item)" size="small" style="flex: 1"
                    @change="(e: Event) => updateArrayItem(sec.key, String(key) + '.' + String(subKey), idx, (e.target as HTMLInputElement).value)" />
                  <a-button type="text" size="small" :disabled="idx === 0"
                    @click="moveArrayItem(sec.key, String(key) + '.' + String(subKey), idx, -1)">
                    <ArrowUpOutlined />
                  </a-button>
                  <a-button type="text" size="small" :disabled="idx === subVal.length - 1"
                    @click="moveArrayItem(sec.key, String(key) + '.' + String(subKey), idx, 1)">
                    <ArrowDownOutlined />
                  </a-button>
                  <a-button type="text" size="small" danger @click="deleteArrayItem(sec.key, String(key) + '.' + String(subKey), idx)">✕</a-button>
                </div>
                <a-button size="small" type="dashed" @click="addArrayItem(sec.key, String(key) + '.' + String(subKey), '')">
                  + {{ t('jsonEditor.addItem') }}
                </a-button>
              </div>
              <!-- 内联 section 对象数组 / Inline section object array -->
              <div v-else-if="isInlineSection(sec.key) && Array.isArray(subVal) && (isObjectArrayField(sec.key, String(key) + '.' + String(subKey)) || (subVal.length > 0 && typeof subVal[0] !== 'string' && typeof subVal[0] !== 'number'))" class="config-array indent-field">
                <label>{{ labelFor(subKey) }}</label>
                <div v-for="(item, idx) in subVal" :key="idx" class="array-item-card">
                  <div class="array-item-card-header">
                    <span>#{{ idx + 1 }}</span>
                    <div class="array-item-card-actions">
                      <a-button type="text" size="small" :disabled="idx === 0"
                        @click="moveArrayItem(sec.key, String(key) + '.' + String(subKey), idx, -1)">
                        <ArrowUpOutlined />
                      </a-button>
                      <a-button type="text" size="small" :disabled="idx === subVal.length - 1"
                        @click="moveArrayItem(sec.key, String(key) + '.' + String(subKey), idx, 1)">
                        <ArrowDownOutlined />
                      </a-button>
                      <a-button type="text" size="small" danger @click="deleteArrayItem(sec.key, String(key) + '.' + String(subKey), idx)">✕</a-button>
                    </div>
                  </div>
                  <template v-for="(fieldVal, fieldKey) in item" :key="String(fieldKey)">
                    <div v-if="typeof fieldVal === 'string' || typeof fieldVal === 'number'" class="config-field" style="margin-left: 8px;">
                      <label>{{ labelFor(fieldKey) }}</label>
                      <a-input-number
                        v-if="typeof fieldVal === 'number'"
                        :value="fieldVal" size="small" style="width: 100%"
                        @change="(v: any) => updateArrayItemField(sec.key, String(key) + '.' + String(subKey), idx, String(fieldKey), v)" />
                      <a-input
                        v-else :value="fieldVal" size="small"
                        @change="(e: Event) => updateArrayItemField(sec.key, String(key) + '.' + String(subKey), idx, String(fieldKey), (e.target as HTMLInputElement).value)" />
                    </div>
                    <div v-else-if="typeof fieldVal === 'boolean'" class="config-field" style="margin-left: 8px;">
                      <label>{{ labelFor(fieldKey) }}</label>
                      <a-switch :checked="fieldVal" size="small"
                        @change="(v: boolean) => updateArrayItemField(sec.key, String(key) + '.' + String(subKey), idx, String(fieldKey), v)" />
                    </div>
                  </template>
                </div>
                <a-button size="small" type="dashed" @click="addArrayItem(sec.key, String(key) + '.' + String(subKey), {})">
                  + {{ t('jsonEditor.addItem') }}
                </a-button>
              </div>
              <!-- 非内联 section：只读文本 + 编辑 / Non-inline: readonly text + edit -->
              <div v-else class="config-field indent-field">
                <label>{{ labelFor(subKey) }}</label>
                <div style="display: flex; align-items: center; gap: 8px;">
                  <span class="config-readonly" style="flex: 1;">{{ formatReadonly(subVal) }}</span>
                  <a-button size="small" type="link" @click="openFieldJsonEditor(sec.key, String(key) + '.' + String(subKey), subVal)">
                    {{ t('jsonEditor.editDetails') }}
                  </a-button>
                </div>
              </div>
            </template>
          </div>

          <!-- 内联 section 的字符串数组编辑 / Inline section string array editing -->
          <div v-else-if="isInlineSection(sec.key) && Array.isArray(val) && !isObjectArrayField(sec.key, String(key)) && (val.length === 0 || typeof val[0] === 'string' || typeof val[0] === 'number')" class="config-array">
            <label>{{ labelFor(key) }}</label>
            <div v-for="(item, idx) in val" :key="idx" class="array-item-row">
              <a-input :value="String(item)" size="small" style="flex: 1"
                @change="(e: Event) => updateArrayItem(sec.key, String(key), idx, (e.target as HTMLInputElement).value)" />
              <a-button type="text" size="small" :disabled="idx === 0"
                @click="moveArrayItem(sec.key, String(key), idx, -1)">
                <ArrowUpOutlined />
              </a-button>
              <a-button type="text" size="small" :disabled="idx === val.length - 1"
                @click="moveArrayItem(sec.key, String(key), idx, 1)">
                <ArrowDownOutlined />
              </a-button>
              <a-button type="text" size="small" danger @click="deleteArrayItem(sec.key, String(key), idx)">✕</a-button>
            </div>
            <a-button size="small" type="dashed" @click="addArrayItem(sec.key, String(key), '')">
              + {{ t('jsonEditor.addItem') }}
            </a-button>
          </div>
          <!-- 内联 section 的对象数组编辑 / Inline section object array editing -->
          <div v-else-if="isInlineSection(sec.key) && Array.isArray(val) && (isObjectArrayField(sec.key, String(key)) || (val.length > 0 && typeof val[0] !== 'string' && typeof val[0] !== 'number'))" class="config-array">
            <label>{{ labelFor(key) }}</label>
            <div v-for="(item, idx) in val" :key="idx" class="array-item-card">
              <div class="array-item-card-header">
                <span>#{{ idx + 1 }}</span>
                <div class="array-item-card-actions">
                  <a-button type="text" size="small" :disabled="idx === 0"
                    @click="moveArrayItem(sec.key, String(key), idx, -1)">
                    <ArrowUpOutlined />
                  </a-button>
                  <a-button type="text" size="small" :disabled="idx === val.length - 1"
                    @click="moveArrayItem(sec.key, String(key), idx, 1)">
                    <ArrowDownOutlined />
                  </a-button>
                  <a-button type="text" size="small" danger @click="deleteArrayItem(sec.key, String(key), idx)">✕</a-button>
                </div>
              </div>
              <template v-for="(fieldVal, fieldKey) in item" :key="String(fieldKey)">
                <div v-if="typeof fieldVal === 'string' || typeof fieldVal === 'number'" class="config-field" style="margin-left: 8px;">
                  <label>{{ labelFor(fieldKey) }}</label>
                  <a-input-number
                    v-if="typeof fieldVal === 'number'"
                    :value="fieldVal" size="small" style="width: 100%"
                    @change="(v: any) => updateArrayItemField(sec.key, String(key), idx, String(fieldKey), v)" />
                  <a-input
                    v-else :value="fieldVal" size="small"
                    @change="(e: Event) => updateArrayItemField(sec.key, String(key), idx, String(fieldKey), (e.target as HTMLInputElement).value)" />
                </div>
                <div v-else-if="typeof fieldVal === 'boolean'" class="config-field" style="margin-left: 8px;">
                  <label>{{ labelFor(fieldKey) }}</label>
                  <a-switch :checked="fieldVal" size="small"
                    @change="(v: boolean) => updateArrayItemField(sec.key, String(key), idx, String(fieldKey), v)" />
                </div>
              </template>
            </div>
            <a-button size="small" type="dashed" @click="addArrayItem(sec.key, String(key), {})">
              + {{ t('jsonEditor.addItem') }}
            </a-button>
          </div>
          <!-- 非内联 section：只读 + JsonEditor / Non-inline: readonly + JsonEditor -->
          <div v-else class="config-field">
            <label>{{ labelFor(key) }}</label>
            <div style="display: flex; align-items: center; gap: 8px;">
              <span class="config-readonly" style="flex: 1;">{{ formatReadonly(val) }}</span>
              <a-button size="small" type="link" @click="openFieldJsonEditor(sec.key, String(key), val)">
                {{ t('jsonEditor.editDetails') }}
              </a-button>
            </div>
          </div>
        </template>
      </a-collapse-panel>
    </a-collapse>

    <!-- JsonEditor 模态框（复杂值编辑）/ JsonEditor modal (complex value editing) -->
    <JsonEditor
      :visible="showJsonEditor"
      :value="editingFieldValue"
      :title="editingSectionKey + '.' + editingFieldKey"
      @confirm="onFieldJsonConfirm"
      @cancel="showJsonEditor = false"
    />
  </div>
</template>

<style scoped>
.config-panel {
  margin-top: 8px;
}
.config-field {
  margin-bottom: 10px;
}
.config-field label {
  display: block;
  font-size: 12px;
  color: #666;
  margin-bottom: 4px;
}
/* 嵌套对象组 / Nested object group */
.config-group {
  margin-top: 6px;
  margin-bottom: 10px;
  padding: 8px 10px;
  border: 1px solid #e8e8e8;
  border-radius: 6px;
  background: #fafafa;
}
.config-group-label {
  font-size: 12px;
  font-weight: 600;
  color: #555;
  display: block;
  margin-bottom: 6px;
}
/* 缩进字段 / Indented field */
.indent-field {
  margin-left: 12px;
}
.indent-group {
  margin-left: 6px;
}
.indent-field-2 {
  margin-left: 24px;
}
/* 只读值 / Readonly value */
.config-readonly {
  font-size: 12px;
  color: #999;
  padding: 4px 8px;
  background: #f5f5f5;
  border-radius: 3px;
  word-break: break-all;
  display: inline-block;
}
/* 数组内联编辑 / Inline array editing */
.config-array {
  margin-bottom: 10px;
}
.array-item-row {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 4px;
  margin-left: 12px;
}
.array-item-card {
  margin: 6px 0 6px 12px;
  padding: 8px;
  border: 1px solid #e8e8e8;
  border-radius: 4px;
  background: #fff;
}
.array-item-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
  font-size: 11px;
  color: #999;
}
/* 对象数组卡片操作按钮组 / Object array card action button group */
.array-item-card-actions {
  display: flex;
  align-items: center;
  gap: 2px;
}
</style>
