<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { useAgentStore } from '../../stores/agent'
import type { AgentCommand, PromptData, PlanReviewData } from '../../types/agent'

const { t } = useI18n()
const agent = useAgentStore()

const props = defineProps<{
  /** 右侧批注器是否可见 / Whether the right annotator is visible */
  annotatorVisible?: boolean
}>()

const emit = defineEmits<{
  /** 切换右侧批注器可见性 / Toggle right annotator visibility */
  toggleAnnotator: []
}>()

const prompt = computed(() => agent.activeTask?.pendingPrompt)

// API 澄清状态 / API clarification state
const clarifyText = ref('')

// 计划审核状态 / Plan review state
const reviewMode = ref<'approve' | 'annotations' | 'text' | null>(null)
const reviewText = ref('')

// 监听新 prompt 到达：重置审核状态
// Watch new prompt arrival: reset review state
watch(() => prompt.value?.id, (newId, oldId) => {
  if (newId && newId !== oldId) {
    reviewMode.value = null
    reviewText.value = ''
  }
})

async function handleSkip() {
  const cmd: AgentCommand = {
    command: 'skip',
    prompt_id: prompt.value?.id || '',
  }
  resetState()
  await agent.sendCommand(agent.activeTaskId!, cmd)
}

async function handleRespond() {
  if (!clarifyText.value.trim()) {
    message.warning(t('agent.prompt_emptyInput'))
    return
  }
  const cmd: AgentCommand = {
    command: 'respond',
    prompt_id: prompt.value?.id || '',
    text: clarifyText.value.trim(),
  }
  resetState()
  await agent.sendCommand(agent.activeTaskId!, cmd)
}

async function handleApprove() {
  const cmd: AgentCommand = {
    command: 'approve',
    prompt_id: prompt.value?.id || '',
  }
  resetState()
  await agent.sendCommand(agent.activeTaskId!, cmd)
}

async function handleReviseAnnotations() {
  const cmd: AgentCommand = {
    command: 'revise_annotations',
    prompt_id: prompt.value?.id || '',
  }
  resetState()
  await agent.sendCommand(agent.activeTaskId!, cmd)
}

async function handleReviseText() {
  if (!reviewText.value.trim()) {
    message.warning(t('agent.prompt_emptyInput'))
    return
  }
  const cmd: AgentCommand = {
    command: 'revise_text',
    prompt_id: prompt.value?.id || '',
    text: reviewText.value.trim(),
  }
  resetState()
  await agent.sendCommand(agent.activeTaskId!, cmd)
}

function resetState() {
  clarifyText.value = ''
  reviewMode.value = null
  reviewText.value = ''
}

function getPromptData(): PromptData | PlanReviewData | null {
  const p = prompt.value
  if (!p) return null
  return p as PromptData | PlanReviewData
}

const promptData = computed(() => getPromptData())
</script>

<template>
  <div class="question-prompt" :class="{ 'is-review': promptData?.kind === 'plan_review' }" v-if="promptData">
    <!-- API 澄清 / API Clarification -->
    <div v-if="promptData?.kind === 'api_clarification'" class="clarify-section">
      <div class="prompt-title">{{ t('agent.prompt_clarificationTitle') }}</div>
      <div class="prompt-message">{{ (promptData as PromptData).message }}</div>

      <div v-if="(promptData as PromptData).data?.uncertainties?.length" class="uncertainties">
        <div
          v-for="(item, i) in (promptData as PromptData).data.uncertainties"
          :key="i"
          class="uncertainty-item"
        >
          <strong>{{ item.api_path }}</strong>
          <span class="issues">{{ item.issues.join(', ') }}</span>
        </div>
      </div>

      <div class="clarify-actions">
        <a-button @click="handleSkip">{{ t('agent.prompt_skip') }}</a-button>
        <a-input
          v-model:value="clarifyText"
          :placeholder="t('agent.prompt_inputHint')"
          style="flex: 1;"
          @keydown.enter="handleRespond"
        />
        <a-button type="primary" @click="handleRespond" :disabled="!clarifyText.trim()">
          {{ t('agent.prompt_confirm') }}
        </a-button>
      </div>
    </div>

    <!-- 计划审核 / Plan Review -->
    <div v-if="promptData?.kind === 'plan_review'" class="review-section">
      <div class="prompt-title">{{ t('agent.prompt_planReviewTitle') }}</div>

      <div class="review-options">
        <a-radio-group v-model:value="reviewMode" style="display: flex; flex-direction: column; gap: 8px;">
          <a-radio value="approve">{{ t('agent.prompt_approve') }}</a-radio>
          <a-radio value="annotations">{{ t('agent.prompt_reviseAnnotate') }}</a-radio>
          <a-radio value="text">
            {{ t('agent.prompt_reviseText') }}
            <a-textarea
              v-if="reviewMode === 'text'"
              v-model:value="reviewText"
              :rows="2"
              style="margin-top: 8px;"
            />
          </a-radio>
        </a-radio-group>
      </div>

      <div class="review-actions">
        <a-button @click="emit('toggleAnnotator')">
          {{ props.annotatorVisible ? 'Hide Plan' : 'View Plan' }}
        </a-button>
        <a-button
          type="primary"
          :disabled="!reviewMode || (reviewMode === 'text' && !reviewText.trim())"
          @click="
            reviewMode === 'approve' ? handleApprove() :
            reviewMode === 'annotations' ? handleReviseAnnotations() :
            handleReviseText()
          "
        >
          {{ t('agent.prompt_confirm') }}
        </a-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.question-prompt {
  border-top: 2px solid #fa8c16;
  padding: 16px;
  background: #fff7e6;
}
/* 计划审核 — 水平分栏时去掉顶部边框，由父组件添加左侧边框 */
/* Plan review — remove top border in horizontal layout; parent adds left border */
.question-prompt.is-review {
  border-top: none;
}
.prompt-title {
  font-weight: 600;
  font-size: 14px;
  margin-bottom: 8px;
  color: #d46b08;
}
.prompt-message {
  font-size: 13px;
  color: #666;
  margin-bottom: 12px;
}
.clarify-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}
.uncertainties {
  margin-bottom: 12px;
  max-height: 150px;
  overflow-y: auto;
}
.uncertainty-item {
  padding: 4px 8px;
  background: #fff;
  border-radius: 4px;
  margin-bottom: 4px;
  font-size: 12px;
}
.uncertainty-item .issues {
  color: #fa8c16;
  margin-left: 8px;
}
.review-options {
  margin-bottom: 12px;
}
.review-actions {
  display: flex;
  gap: 8px;
}
</style>
