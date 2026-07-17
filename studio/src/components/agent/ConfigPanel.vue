<script setup lang="ts">
// ConfigPanel — 动态配置节编辑器。根据实际 configData 渲染所有键值，取代预定义字段列表。
// Dynamic config section editor. Renders all keys from actual configData, replacing predefined field lists.
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import JsonEditor from '../json-editor/JsonEditor.vue'
import { normalizeJsonValue } from '../../utils/json-helper'

const { t } = useI18n()

const props = defineProps<{
  configData: Record<string, any>
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
const sections = [
  { key: 'pipeline', label: t('agent.config_pipeline') },
  { key: 'validation', label: t('agent.config_validation') },
  { key: 'plugins', label: t('agent.config_plugins') },
  { key: 'skills', label: t('agent.config_skills') },
  { key: 'logging', label: t('agent.config_logging') },
]

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
            <label>{{ key }}</label>
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
              @change="e => {
                const target = e.target as HTMLInputElement
                emitChange(sec.key, key, target.value)
              }"
            />
          </div>

          <!-- 布尔：开关 / Boolean: switch -->
          <div v-else-if="isBool(val)" class="config-field">
            <label>{{ key }}</label>
            <a-switch
              :checked="val"
              size="small"
              @change="(v: boolean) => emitChange(sec.key, key, v)"
            />
          </div>

          <!-- 嵌套对象：展开子属性 / Nested object: expand sub-properties -->
          <div v-else-if="isNestedObject(val)" class="config-group">
            <span class="config-group-label">{{ key }}</span>
            <template v-for="(subVal, subKey) in val" :key="String(subKey)">
              <div v-if="isScalar(subVal)" class="config-field indent-field">
                <label>{{ subKey }}</label>
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
                  @change="e => {
                    const target = e.target as HTMLInputElement
                    emitChange(sec.key, key + '.' + subKey, target.value)
                  }"
                />
              </div>
              <!-- 二级嵌套对象：递归展开 / Second-level nested: recurse -->
              <div v-else-if="isNestedObject(subVal)" class="config-group indent-group">
                <span class="config-group-label">{{ subKey }}</span>
                <div
                  v-for="(subSubVal, subSubKey) in subVal"
                  :key="String(subSubKey)"
                  class="config-field indent-field-2"
                >
                  <label>{{ subSubKey }}</label>
                  <a-input
                    v-if="isScalar(subSubVal)"
                    :value="String(subSubVal)"
                    size="small"
                    @change="e => {
                      const target = e.target as HTMLInputElement
                      emitChange(sec.key, key + '.' + subKey + '.' + subSubKey, target.value)
                    }"
                  />
                  <a-switch
                    v-else-if="isBool(subSubVal)"
                    :checked="subSubVal"
                    size="small"
                    @change="(v: boolean) => emitChange(sec.key, key + '.' + subKey + '.' + subSubKey, v)"
                  />
                  <div v-else style="display: flex; align-items: center; gap: 4px;">
                    <span class="config-readonly" style="flex: 1;">{{ formatReadonly(subSubVal) }}</span>
                    <a-button size="small" type="link" @click="openFieldJsonEditor(sec.key, String(key) + '.' + String(subKey), subSubVal)">
                      {{ t('jsonEditor.editDetails') }}
                    </a-button>
                  </div>
                </div>
              </div>
              <div v-else-if="isBool(subVal)" class="config-field indent-field">
                <label>{{ subKey }}</label>
                <a-switch
                  :checked="subVal"
                  size="small"
                  @change="(v: boolean) => emitChange(sec.key, key + '.' + subKey, v)"
                />
              </div>
              <!-- 数组/其他：只读文本 / Array/other: readonly text -->
              <div v-else class="config-field indent-field">
                <label>{{ subKey }}</label>
                <span class="config-readonly">{{ formatReadonly(subVal) }}</span>
              </div>
            </template>
          </div>

          <!-- 数组/其他：只读文本 + 编辑按钮 / Array/other: readonly text + edit button -->
          <div v-else class="config-field">
            <label>{{ key }}</label>
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
</style>
