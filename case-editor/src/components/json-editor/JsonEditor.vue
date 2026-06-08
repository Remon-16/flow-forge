<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { JsonNode } from '../../types/excel'
import { parseJsonToNodes, nodesToJson, plainToJsonNode } from '../../utils/json-helper'
import JsonNodeComponent from './JsonNode.vue'

const props = defineProps<{
  visible: boolean
  value: Record<string, unknown>
  title: string
}>()

const emit = defineEmits<{
  confirm: [value: Record<string, unknown>]
  cancel: []
}>()

const { t } = useI18n()

const pasteText = ref('')
const nodes = ref<JsonNode[]>([])
const parseError = ref('')

watch(
  () => [props.visible, props.value],
  () => {
    if (props.visible) {
      pasteText.value = ''
      parseError.value = ''
      nodes.value = buildNodesFromValue(props.value)
    }
  }
)

function buildNodesFromValue(val: Record<string, unknown>): JsonNode[] {
  if (!val || Object.keys(val).length === 0) return []
  return Object.entries(val).map(([k, v]) => plainToJsonNode(k, v))
}

function handleParse() {
  parseError.value = ''
  const parsed = parseJsonToNodes(pasteText.value)
  if (parsed.length === 0 && pasteText.value.trim()) {
    try {
      JSON.parse(pasteText.value)
      nodes.value = []
    } catch {
      parseError.value = t('jsonEditor.parseError')
      return
    }
  }
  nodes.value = parsed
}

function handleConfirm() {
  const result: Record<string, unknown> = {}
  for (const node of nodes.value) {
    result[node.key] = nodeToPlain(node)
  }
  emit('confirm', result)
}

function nodeToPlain(node: JsonNode): unknown {
  switch (node.type) {
    case 'string': return String(node.value)
    case 'number': return Number(node.value)
    case 'boolean': return node.value === true || node.value === 'true'
    case 'Date': return String(node.value)
    case 'List': return (node.value as JsonNode[]).map(n => nodeToPlain(n))
    case 'Dict': {
      const obj: Record<string, unknown> = {}
      for (const child of (node.value as JsonNode[])) {
        obj[child.key] = nodeToPlain(child)
      }
      return obj
    }
    default: return String(node.value)
  }
}

function addField() {
  nodes.value.push({
    key: '',
    type: 'string',
    value: '',
  })
}

function removeNode(idx: number) {
  nodes.value.splice(idx, 1)
}

function updateNodeKey(idx: number, key: string) {
  nodes.value[idx].key = key
}

function updateNodeType(idx: number, type: string) {
  const node = nodes.value[idx]
  node.type = type as JsonNode['type']
  // Reset value on type change
  switch (type) {
    case 'string': node.value = ''; break
    case 'number': node.value = 0; break
    case 'boolean': node.value = false; break
    case 'Date': node.value = ''; break
    case 'List': node.value = []; break
    case 'Dict': node.value = []; break
  }
}

function updateNodeValue(idx: number, value: unknown) {
  nodes.value[idx].value = value as string
}
</script>

<template>
  <a-modal
    :open="visible"
    :title="t('jsonEditor.title') + ' — ' + (title || '')"
    width="700px"
    @ok="handleConfirm"
    @cancel="emit('cancel')"
    :okText="t('jsonEditor.confirm')"
    :cancelText="t('jsonEditor.cancel')"
  >
    <!-- Paste area -->
    <div style="margin-bottom: 12px;">
      <a-textarea
        v-model:value="pasteText"
        :placeholder="t('jsonEditor.pasteHint')"
        :rows="3"
        style="font-family: monospace; font-size: 12px;"
      />
      <div style="margin-top: 4px; display: flex; gap: 8px; align-items: center;">
        <a-button size="small" @click="handleParse">
          {{ t('jsonEditor.parse') }}
        </a-button>
        <span v-if="parseError" style="color: #ff4d4f; font-size: 12px;">
          {{ parseError }}
        </span>
      </div>
    </div>

    <!-- Tree editor -->
    <div class="json-editor-tree">
      <div v-if="nodes.length === 0" style="color: #999; text-align: center; padding: 20px;">
        {{ pasteText ? t('jsonEditor.parseError') : '{}' }}
      </div>

      <JsonNodeComponent
        v-for="(node, idx) in nodes"
        :key="idx"
        :node="node"
        :index="idx"
        :depth="0"
        :is-list-item="false"
        @update:key="(k: string) => updateNodeKey(idx, k)"
        @update:type="(t: string) => updateNodeType(idx, t)"
        @update:value="(v: unknown) => updateNodeValue(idx, v)"
        @remove="() => removeNode(idx)"
      />

      <a-button
        v-if="nodes.length > 0"
        size="small"
        type="dashed"
        block
        style="margin-top: 8px;"
        @click="addField"
      >
        + {{ t('jsonEditor.addField') }}
      </a-button>
    </div>
  </a-modal>
</template>
