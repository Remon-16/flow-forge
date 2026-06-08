<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  type: string
  value: unknown
  isListItem: boolean
}>()

const emit = defineEmits<{
  'update:value': [value: unknown]
}>()

const stringValue = computed(() => String(props.value ?? ''))

function onInputChange(e: Event) {
  const target = e.target as HTMLInputElement
  emit('update:value', target.value)
}

function onNumberChange(val: number | null) {
  emit('update:value', val ?? 0)
}

function onBooleanChange(val: string) {
  emit('update:value', val === 'true')
}

function onDateChange(_date: unknown, dateString: string | string[]) {
  emit('update:value', Array.isArray(dateString) ? dateString[0] : dateString)
}
</script>

<template>
  <!-- String -->
  <a-input
    v-if="type === 'string'"
    :value="stringValue"
    size="small"
    style="width: 100%;"
    @change="onInputChange"
  />

  <!-- Number -->
  <a-input-number
    v-else-if="type === 'number'"
    :value="Number(value ?? 0)"
    size="small"
    style="width: 100%;"
    @change="onNumberChange"
  />

  <!-- Boolean -->
  <a-select
    v-else-if="type === 'boolean'"
    :value="String(value ?? false)"
    size="small"
    style="width: 100%;"
    @change="onBooleanChange"
  >
    <a-select-option value="true">true</a-select-option>
    <a-select-option value="false">false</a-select-option>
  </a-select>

  <!-- Date -->
  <a-date-picker
    v-else-if="type === 'Date'"
    :value="stringValue ? stringValue : undefined"
    size="small"
    style="width: 100%;"
    @change="onDateChange"
  />

  <!-- Fallback -->
  <a-input
    v-else
    :value="stringValue"
    size="small"
    style="width: 100%;"
    @change="onInputChange"
  />
</template>
