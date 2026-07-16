<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const props = defineProps<{
  configData: Record<string, any>
}>()

const emit = defineEmits<{
  change: [key: string, value: any]
}>()

// 默认折叠 / Collapsed by default
const activeKeys = ref<string[]>([])

// 配置节定义 / Config section definitions
const sections: { key: string; label: string; fields: { key: string; label: string; type: string }[] }[] = [
  {
    key: 'pipeline',
    label: 'Pipeline',
    fields: [
      { key: 'max_steps', label: 'Max Steps', type: 'number' },
      { key: 'max_retries', label: 'Max Retries', type: 'number' },
      { key: 'skeleton_batch_size', label: 'Skeleton Batch Size', type: 'number' },
      { key: 'plan_single_batch_size', label: 'Plan Single Batch Size', type: 'number' },
      { key: 'plugin_batch_size', label: 'Plugin Batch Size', type: 'number' },
      { key: 'consecutive_batch_failure_limit', label: 'Batch Failure Limit', type: 'number' },
      { key: 'max_steps_no_progress', label: 'Max Steps No Progress', type: 'number' },
      { key: 'case_type', label: 'Case Type', type: 'select', options: ['both', 'single', 'biz'] },
      { key: 'auto', label: 'Auto Mode', type: 'boolean' },
    ],
  },
  {
    key: 'validation',
    label: 'Validation',
    fields: [],
  },
  {
    key: 'plugins',
    label: 'Plugins',
    fields: [
      { key: 'enabled', label: 'Enabled', type: 'boolean' },
    ],
  },
  {
    key: 'skills',
    label: 'Skills',
    fields: [
      { key: 'enabled', label: 'Enabled', type: 'boolean' },
    ],
  },
  {
    key: 'logging',
    label: 'Logging',
    fields: [
      { key: 'log_to_output', label: 'Log to Output', type: 'boolean' },
    ],
  },
]

function getValue(sectionKey: string, fieldKey: string): any {
  const section = props.configData?.[sectionKey]
  if (section && typeof section === 'object') {
    return section[fieldKey]
  }
  return undefined
}

function setValue(sectionKey: string, fieldKey: string, val: any) {
  emit('change', `${sectionKey}.${fieldKey}`, val)
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
        <div v-if="sec.fields.length === 0" style="color: #999; font-size: 12px;">
          Configuration passed as-is from env.yaml
        </div>
        <div v-for="f in sec.fields" :key="f.key" class="config-field">
          <label>{{ f.label }}</label>
          <a-input-number
            v-if="f.type === 'number'"
            :value="getValue(sec.key, f.key)"
            size="small"
            style="width: 100%"
            @change="(v: any) => setValue(sec.key, f.key, v)"
          />
          <a-switch
            v-else-if="f.type === 'boolean'"
            :checked="getValue(sec.key, f.key)"
            size="small"
            @change="(v: boolean) => setValue(sec.key, f.key, v)"
          />
          <a-select
            v-else-if="f.type === 'select'"
            :value="getValue(sec.key, f.key)"
            size="small"
            style="width: 100%"
            :options="(f as any).options?.map((o: string) => ({ value: o, label: o }))"
            @change="(v: string) => setValue(sec.key, f.key, v)"
          />
        </div>
      </a-collapse-panel>
    </a-collapse>
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
</style>
