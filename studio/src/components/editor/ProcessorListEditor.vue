<template>
  <div class="processor-list-editor">
    <div class="processor-toolbar">
      <a-button size="small" @click="addItem">
        <PlusOutlined /> {{ t('processor.addItem') }}
      </a-button>
      <a-button size="small" @click="showPasteModal = true">
        {{ t('processor.pasteJson') }}
      </a-button>
    </div>

    <div v-if="!items.length" class="processor-empty">
      {{ t('processor.noItems') }}
    </div>

    <div v-else class="processor-items">
      <div
        v-for="(item, idx) in items"
        :key="idx"
        class="processor-item"
      >
        <div class="processor-item-header">
          <span class="processor-index">#{{ idx + 1 }}</span>
          <a-input
            :value="item.name"
            :placeholder="t('processor.name')"
            size="small"
            class="processor-name-input"
            :status="nameError(idx) ? 'error' : ''"
            @change="(e: any) => updateName(idx, e.target.value)"
          />
          <a-button size="small" type="text" @click="toggleConfig(idx)">
            <SettingOutlined />
          </a-button>
          <a-button size="small" type="text" :disabled="idx === 0" @click="moveItem(idx, -1)">
            <ArrowUpOutlined />
          </a-button>
          <a-button size="small" type="text" :disabled="idx === items.length - 1" @click="moveItem(idx, 1)">
            <ArrowDownOutlined />
          </a-button>
          <a-popconfirm
            :title="t('processor.removeItem') + '?'"
            @confirm="removeItem(idx)"
          >
            <a-button size="small" type="text" danger>
              <DeleteOutlined />
            </a-button>
          </a-popconfirm>
        </div>

        <div v-if="expandedIdx === idx" class="processor-config">
          <div class="config-toolbar">
            <span class="config-label">{{ t('processor.config') }}</span>
            <a-button size="small" type="link" @click="addConfig(idx)">
              <PlusOutlined /> {{ t('processor.addConfig') }}
            </a-button>
          </div>
          <div
            v-for="(cfg, cfgIdx) in item.configEntries || []"
            :key="cfgIdx"
            class="config-row"
          >
            <a-input
              :value="cfg.key"
              :placeholder="t('processor.configKey')"
              size="small"
              class="config-key"
              @change="(e: any) => updateConfigKey(idx, cfgIdx, e.target.value)"
            />
            <span class="config-eq">=</span>
            <a-input
              :value="cfg.value"
              :placeholder="t('processor.configValue')"
              size="small"
              class="config-value"
              @change="(e: any) => updateConfigValue(idx, cfgIdx, e.target.value)"
            />
            <a-button size="small" type="text" danger @click="removeConfig(idx, cfgIdx)">
              <DeleteOutlined />
            </a-button>
          </div>
        </div>

        <div v-if="nameError(idx)" class="processor-error">
          {{ t('validator.processorNameRequired') }}
        </div>
      </div>
    </div>

    <!-- Paste JSON modal -->
    <a-modal
      :title="title"
      :open="showPasteModal"
      :footer="null"
      @cancel="showPasteModal = false"
    >
      <a-textarea
        v-model:value="pasteText"
        :rows="8"
        :placeholder="'[\n  {\"name\": \"...\", \"config\": {\"key\": \"value\"}}\n]'"
      />
      <div class="paste-actions">
        <a-button @click="showPasteModal = false">{{ t('common.cancel') }}</a-button>
        <a-button type="primary" @click="handlePaste">{{ t('common.ok') }}</a-button>
      </div>
      <div v-if="pasteError" class="paste-error">{{ pasteError }}</div>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import {
  PlusOutlined,
  SettingOutlined,
  ArrowUpOutlined,
  ArrowDownOutlined,
  DeleteOutlined,
} from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'
import type { PreProcessorItem } from '@/types/excel'

const { t } = useI18n()

interface ConfigEntry {
  key: string
  value: string
}

interface EditableItem extends PreProcessorItem {
  configEntries?: ConfigEntry[]
}

const props = defineProps<{
  modelValue: PreProcessorItem[] | null
  title: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: PreProcessorItem[] | null): void
}>()

// Expand state
const expandedIdx = ref<number | null>(null)

// Paste modal
const showPasteModal = ref(false)
const pasteText = ref('')
const pasteError = ref('')

// Items
const items = ref<EditableItem[]>([])

function rebuildItems() {
  const raw = props.modelValue || []
  items.value = raw.map((item) => {
    const configEntries: ConfigEntry[] = []
    if (item.config && typeof item.config === 'object') {
      for (const [k, v] of Object.entries(item.config)) {
        configEntries.push({ key: k, value: String(v ?? '') })
      }
    }
    return { ...item, configEntries }
  })
}

watch(() => props.modelValue, rebuildItems, { immediate: true })

function emitUpdate() {
  const result: PreProcessorItem[] = items.value.map((item) => {
    const config: Record<string, string> = {}
    if (item.configEntries) {
      for (const entry of item.configEntries) {
        if (entry.key.trim()) {
          config[entry.key.trim()] = entry.value
        }
      }
    }
    return {
      name: item.name,
      config: Object.keys(config).length > 0 ? config : undefined,
    }
  })
  emit('update:modelValue', result)
}

// CRUD
function addItem() {
  items.value.push({ name: '', configEntries: [] })
  emitUpdate()
}

function removeItem(idx: number) {
  items.value.splice(idx, 1)
  if (expandedIdx.value === idx) expandedIdx.value = null
  emitUpdate()
}

function moveItem(idx: number, delta: number) {
  const target = idx + delta
  if (target < 0 || target >= items.value.length) return
  const tmp = items.value[idx]
  items.value[idx] = items.value[target]
  items.value[target] = tmp
  emitUpdate()
}

function updateName(idx: number, value: string) {
  items.value[idx].name = value
  emitUpdate()
}

function toggleConfig(idx: number) {
  expandedIdx.value = expandedIdx.value === idx ? null : idx
}

function addConfig(idx: number) {
  const item = items.value[idx]
  if (!item.configEntries) item.configEntries = []
  item.configEntries.push({ key: '', value: '' })
}

function updateConfigKey(idx: number, cfgIdx: number, value: string) {
  const item = items.value[idx]
  if (item.configEntries) {
    item.configEntries[cfgIdx].key = value
    emitUpdate()
  }
}

function updateConfigValue(idx: number, cfgIdx: number, value: string) {
  const item = items.value[idx]
  if (item.configEntries) {
    item.configEntries[cfgIdx].value = value
    emitUpdate()
  }
}

function removeConfig(idx: number, cfgIdx: number) {
  const item = items.value[idx]
  if (item.configEntries) {
    item.configEntries.splice(cfgIdx, 1)
    emitUpdate()
  }
}

// Validation
function nameError(idx: number): boolean {
  const item = items.value[idx]
  return item.name !== undefined && item.name.trim() === '' && items.value.length > 0
}

// Paste JSON
function handlePaste() {
  pasteError.value = ''
  try {
    const parsed = JSON.parse(pasteText.value)
    if (!Array.isArray(parsed)) {
      pasteError.value = t('processor.parseError')
      return
    }
    for (const entry of parsed) {
      if (!entry.name || typeof entry.name !== 'string') {
        pasteError.value = t('validator.processorNameRequired')
        return
      }
    }
    const newItems: EditableItem[] = parsed.map((entry: any) => {
      const configEntries: ConfigEntry[] = []
      if (entry.config && typeof entry.config === 'object') {
        for (const [k, v] of Object.entries(entry.config)) {
          configEntries.push({ key: k, value: String(v ?? '') })
        }
      }
      return { name: entry.name, config: entry.config, configEntries }
    })
    items.value = newItems
    emitUpdate()
    showPasteModal.value = false
    pasteText.value = ''
  } catch {
    pasteError.value = t('processor.parseError')
  }
}
</script>

<style scoped>
.processor-list-editor {
  width: 100%;
}
.processor-toolbar {
  margin-bottom: 8px;
  display: flex;
  gap: 8px;
}
.processor-empty {
  color: #999;
  font-size: 13px;
  padding: 8px 0;
}
.processor-items {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.processor-item {
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  padding: 6px 8px;
}
.processor-item-header {
  display: flex;
  align-items: center;
  gap: 6px;
}
.processor-index {
  font-size: 12px;
  color: #999;
  min-width: 22px;
}
.processor-name-input {
  flex: 1;
}
.processor-config {
  margin-top: 8px;
  padding: 8px;
  background: #fafafa;
  border-radius: 4px;
}
.config-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}
.config-label {
  font-size: 12px;
  color: #666;
  font-weight: 500;
}
.config-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}
.config-key {
  flex: 1;
}
.config-value {
  flex: 2;
}
.config-eq {
  color: #999;
}
.processor-error {
  color: #ff4d4f;
  font-size: 12px;
  margin-top: 4px;
}
.paste-actions {
  margin-top: 12px;
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}
.paste-error {
  color: #ff4d4f;
  font-size: 12px;
  margin-top: 8px;
}
</style>
