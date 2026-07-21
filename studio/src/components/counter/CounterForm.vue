<script setup lang="ts">
// CounterForm — 诊断计数器配置表单。
// Diagnostic counter config form: output directory + submit button.
// 对应 ExecutorForm.vue 的极简版 / Minimal version of ExecutorForm.vue.
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useCounterStore } from '../../stores/counter'
import { openDirectoryDialog } from '../../utils/desktop-bridge'
import { message } from 'ant-design-vue'

const { t } = useI18n()
const counter = useCounterStore()

const outputDir = ref('')

async function browseOutputDir() {
  try {
    const dir = await openDirectoryDialog()
    if (dir) outputDir.value = dir
  } catch { /* cancelled */ }
}

async function handleSubmit() {
  if (!outputDir.value.trim()) {
    message.warning(t('counter.outputDirRequired'))
    return
  }

  const sessionId = counter.createSession(outputDir.value.trim())
  await counter.startSession(sessionId)
}
</script>

<template>
  <div class="form">
    <!-- 输出目录 / Output directory -->
    <div class="form-section">
      <label class="section-title">{{ t('counter.outputDir') }}</label>
      <p class="section-desc">{{ t('counter.outputDirDesc') }}</p>
      <a-input-group compact>
        <a-input v-model:value="outputDir" :placeholder="t('counter.outputDirPlaceholder')" style="width: calc(100% - 80px)" />
        <a-button @click="browseOutputDir">{{ t('agent.settings_browse') }}</a-button>
      </a-input-group>
    </div>

    <!-- 提交 / Submit -->
    <div class="form-footer">
      <a-button type="primary" size="large" block @click="handleSubmit">
        ▶ {{ t('counter.submit') }}
      </a-button>
    </div>
  </div>
</template>

<style scoped>
.form {
  padding: 24px;
  overflow-y: auto;
  height: 100%;
  display: flex;
  flex-direction: column;
}
.form-section {
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid #f0f0f0;
}
.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #333;
}
.section-desc {
  font-size: 12px;
  color: #999;
  margin: 4px 0 8px 0;
}
.form-footer {
  margin-top: auto;
  padding-top: 16px;
}
</style>
