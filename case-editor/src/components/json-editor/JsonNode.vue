<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { JsonNode, JsonType } from '../../types/excel'
import ValueInput from './ValueInput.vue'

const props = defineProps<{
  node: JsonNode
  index: number
  depth: number
  isListItem: boolean
}>()

const emit = defineEmits<{
  'update:key': [value: string]
  'update:type': [value: string]
  'update:value': [value: unknown]
  remove: []
}>()

const { t } = useI18n()

const collapsed = ref(false)
const maxDepth = 10

const showChildren = computed(() => {
  return (props.node.type === 'Dict' || props.node.type === 'List') && !collapsed.value
})

const canAddChild = computed(() => props.depth < maxDepth)

const typeOptions = [
  { value: 'string', label: t('jsonEditor.types.string') },
  { value: 'number', label: t('jsonEditor.types.number') },
  { value: 'boolean', label: t('jsonEditor.types.boolean') },
  { value: 'Date', label: t('jsonEditor.types.Date') },
  { value: 'List', label: t('jsonEditor.types.List') },
  { value: 'Dict', label: t('jsonEditor.types.Dict') },
]

function onTypeChange(newType: string) {
  emit('update:type', newType)
}

function onValueChange(newVal: unknown) {
  emit('update:value', newVal)
}

function addChildItem() {
  if (!canAddChild.value) return
  const children = props.node.value as JsonNode[]
  const newItem: JsonNode = props.node.type === 'Dict'
    ? { key: '', type: 'string', value: '' }
    : { key: String(children.length), type: 'string', value: '' }
  emit('update:value', [...children, newItem])
}

function updateChild(index: number, updates: Partial<JsonNode>) {
  const children = [...(props.node.value as JsonNode[])]
  children[index] = { ...children[index], ...updates }
  emit('update:value', children)
}

function removeChild(index: number) {
  const children = [...(props.node.value as JsonNode[])]
  children.splice(index, 1)
  emit('update:value', children)
}

// For List items, the value can be complex
function updateListItem(value: unknown) {
  emit('update:value', value)
}
</script>

<template>
  <div>
    <!-- Row: key | type | value -->
    <div class="json-node-row">
      <!-- Key (hidden for list items) -->
      <div v-if="!isListItem" class="key-col">
        <a-input
          :value="node.key"
          size="small"
          placeholder="key"
          style="font-weight: 500;"
          @change="(e: any) => emit('update:key', e.target.value)"
        />
      </div>
      <div v-else class="key-col" style="min-width: 40px; color: #999; font-size: 12px;">
        [{{ index }}]
      </div>

      <!-- Type selector -->
      <div class="type-col">
        <a-select
          :value="node.type"
          size="small"
          style="width: 100%;"
          @change="onTypeChange"
        >
          <a-select-option
            v-for="opt in typeOptions"
            :key="opt.value"
            :value="opt.value"
          >
            {{ opt.label }}
          </a-select-option>
        </a-select>
      </div>

      <!-- Value input -->
      <div class="value-col">
        <!-- Dict / List: collapse control -->
        <template v-if="node.type === 'Dict' || node.type === 'List'">
          <a-button
            size="small"
            type="text"
            style="padding: 0 4px;"
            @click="collapsed = !collapsed"
          >
            {{ collapsed ? '▶' : '▼' }}
          </a-button>
          <span style="color: #999; font-size: 12px; margin-left: 4px;">
            {{ node.type === 'Dict' ? '{' : '[' }}
            {{ (node.value as JsonNode[]).length }} items
            {{ node.type === 'Dict' ? '}' : ']' }}
          </span>
        </template>

        <!-- Primitive values -->
        <ValueInput
          v-else
          :type="node.type"
          :value="node.value"
          :is-list-item="isListItem"
          @update:value="onValueChange"
        />
      </div>

      <!-- Delete button -->
      <a-button size="small" type="text" danger @click="emit('remove')">
        {{ t('jsonEditor.delete') }}
      </a-button>
    </div>

    <!-- Children (Dict / List) -->
    <div v-if="showChildren" class="json-node-children">
      <JsonNode
        v-for="(child, childIdx) in (node.value as JsonNode[])"
        :key="childIdx"
        :node="child"
        :index="childIdx"
        :depth="depth + 1"
        :is-list-item="node.type === 'List'"
        @update:key="(k: string) => updateChild(childIdx, { key: k })"
        @update:type="(t: string) => updateChild(childIdx, { type: t as JsonType })"
        @update:value="(v: unknown) => updateChild(childIdx, { value: v as JsonNode['value'] })"
        @remove="() => removeChild(childIdx)"
      />

      <!-- Add child button -->
      <div
        v-if="canAddChild"
        style="padding: 4px 0;"
      >
        <a-button
          size="small"
          type="dashed"
          @click="addChildItem"
        >
          + {{ node.type === 'Dict' ? t('jsonEditor.addField') : t('jsonEditor.addItem') }}
        </a-button>
      </div>
    </div>
  </div>
</template>
