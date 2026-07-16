<script setup lang="ts">
import { ref, computed } from 'vue'
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
const sections = computed(() => [
  {
    key: 'pipeline',
    label: t('agent.config_pipeline'),
    fields: [
      { key: 'max_steps', label: t('agent.config_maxSteps'), type: 'number' },
      { key: 'max_retries', label: t('agent.config_maxRetries'), type: 'number' },
      { key: 'skeleton_batch_size', label: t('agent.config_skeletonBatchSize'), type: 'number' },
      { key: 'plan_single_batch_size', label: t('agent.config_planSingleBatchSize'), type: 'number' },
      { key: 'plugin_batch_size', label: t('agent.config_pluginBatchSize'), type: 'number' },
      { key: 'consecutive_batch_failure_limit', label: t('agent.config_batchFailureLimit'), type: 'number' },
      { key: 'max_steps_no_progress', label: t('agent.config_maxStepsNoProgress'), type: 'number' },
      { key: 'case_type', label: t('agent.config_caseType'), type: 'select', options: ['both', 'single', 'biz'] },
      { key: 'auto', label: t('agent.config_autoMode'), type: 'boolean' },
    ],
  },
  {
    key: 'validation',
    label: t('agent.config_validation'),
    fields: [],
  },
  {
    key: 'plugins',
    label: t('agent.config_plugins'),
    fields: [
      { key: 'enabled', label: t('agent.config_enabled'), type: 'boolean' },
    ],
  },
  {
    key: 'skills',
    label: t('agent.config_skills'),
    fields: [
      { key: 'enabled', label: t('agent.config_enabled'), type: 'boolean' },
    ],
  },
  {
    key: 'logging',
    label: t('agent.config_logging'),
    fields: [
      { key: 'log_to_output', label: t('agent.config_logToOutput'), type: 'boolean' },
    ],
  },
] as const)

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
          {{ t('agent.config_emptyHint') }}
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
            :options="(f as any).options?.map((o: string) => ({ value: o, label: t('agent.config_' + o) }))"
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
