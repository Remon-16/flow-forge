<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useAgentStore } from '../../stores/agent'
import type { CompletionSummary } from '../../types/agent'
import { openInExplorer } from '../../utils/desktop-bridge'

const { t } = useI18n()
const agent = useAgentStore()

const summary = (): CompletionSummary | undefined => agent.activeTask?.summary

function handleOpenDir(dir: string) {
  openInExplorer(dir).catch(() => {})
}
</script>

<template>
  <div class="completed-view">
    <div class="complete-header">
      <span style="font-size: 40px;">✓</span>
      <h4 style="margin: 0; color: #52c41a;">{{ t('agent.status_completed') }}</h4>
    </div>

    <div class="summary-cards" v-if="summary()">
      <a-card size="small">
        <a-statistic
          :title="t('agent.complete_singleCases')"
          :value="summary()?.single_cases ?? 0"
        />
      </a-card>
      <a-card size="small">
        <a-statistic
          :title="t('agent.complete_bizFlows')"
          :value="summary()?.biz_flows ?? 0"
        />
      </a-card>
      <a-card size="small">
        <a-statistic
          :title="t('agent.complete_interfaces')"
          :value="summary()?.interfaces ?? 0"
        />
      </a-card>
    </div>

    <div class="output-location" v-if="summary()?.output_dir">
      <span>{{ t('agent.complete_outputDir') }}:</span>
      <a-button
        type="link"
        size="small"
        @click="handleOpenDir(summary()!.output_dir)"
      >
        {{ summary()?.output_dir }}
      </a-button>
    </div>
  </div>
</template>

<style scoped>
.completed-view {
  padding: 32px;
  text-align: center;
}
.complete-header {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  margin-bottom: 24px;
}
.summary-cards {
  display: flex;
  justify-content: center;
  gap: 16px;
  margin-bottom: 24px;
}
.summary-cards .ant-card {
  min-width: 140px;
}
.output-location {
  color: #666;
  font-size: 13px;
}
</style>
