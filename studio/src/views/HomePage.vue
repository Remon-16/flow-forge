<script setup lang="ts">
// HomePage — 首页，3 列入口卡片（生成 → 编辑 → 执行），含设置/退出按钮。
// Homepage with 3-column entry cards (Generate → Edit → Execute), plus settings/exit buttons.
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { SettingOutlined } from '@ant-design/icons-vue'
import { useSettingsStore } from '../stores/settings'
import AgentSettings from '../components/agent/AgentSettings.vue'
import { ENABLE_DIAGNOSTICS } from '../utils/feature-flags'

const router = useRouter()
const { t } = useI18n()
const settings = useSettingsStore()

// 设置弹窗可见性 / Settings modal visibility
const settingsVisible = ref(false)

function goExcel() {
  router.push('/excel')
}

function goYaml() {
  router.push('/yaml')
}

function goPlanAnnotator() {
  router.push('/plan-annotator')
}

function goAgent() {
  router.push('/agent')
}

function goExecutor() {
  router.push('/executor')
}

function goConverter() {
  router.push('/converter')
}

function goCounter() {
  router.push('/counter')
}

function handleLanguageChange(lang: string) {
  settings.setLanguage(lang as 'zh-CN' | 'en-US')
}
</script>

<template>
  <div class="home-page">
    <!-- 右上角操作栏：语言切换 + 设置 + 退出 / Top-right action bar: language + settings + exit -->
    <div class="home-actions">
      <a-select
        :value="settings.language"
        size="small"
        style="width: 90px"
        @change="handleLanguageChange"
      >
        <a-select-option value="zh-CN">中文</a-select-option>
        <a-select-option value="en-US">English</a-select-option>
      </a-select>
      <a-button class="action-btn" :title="t('home.settings')" @click="settingsVisible = true">
        <SettingOutlined />
      </a-button>
    </div>

    <div class="home-header">
      <h1 class="home-title">{{ t('home.title') }}</h1>
      <p class="home-subtitle">{{ t('home.subtitle') }}</p>
    </div>

    <!-- 3 列水平布局 / Three-column horizontal layout -->
    <div class="home-columns">
      <!-- ① 用例生成 / Generate -->
      <div class="home-column">
        <div class="section-label generate-label">{{ t('home.sectionGenerate') }}</div>
        <a-card hoverable class="home-card" :body-style="{ padding: 0 }" @click="goAgent">
          <div class="card-icon agent-icon">
            <svg viewBox="0 0 24 24" width="40" height="40" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="8.5" />
              <path d="M12 7v5l4 2" />
              <path d="M8 14c-1.5-2.5 1-5 4-5s5.5 2.5 4 5" />
            </svg>
          </div>
          <h3>{{ t('home.agentTitle') }}</h3>
          <p>{{ t('home.agentDesc') }}</p>
        </a-card>

        <a-card hoverable class="home-card" :body-style="{ padding: 0 }" @click="goPlanAnnotator">
          <div class="card-icon annotator-icon">
            <svg viewBox="0 0 24 24" width="40" height="40" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 20h9" />
              <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
            </svg>
          </div>
          <h3>{{ t('home.annotatorTitle') }}</h3>
          <p>{{ t('home.annotatorDesc') }}</p>
        </a-card>
      </div>

      <!-- 列间箭头 / Between-column arrow -->
      <div class="column-arrow">→</div>

      <!-- ② 用例编辑 / Edit -->
      <div class="home-column">
        <div class="section-label edit-label">{{ t('home.sectionEdit') }}</div>
        <a-card hoverable class="home-card" :body-style="{ padding: 0 }" @click="goExcel">
          <div class="card-icon excel-icon">
            <svg viewBox="0 0 24 24" width="40" height="40" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="3" y="3" width="18" height="18" rx="2" />
              <path d="M8 8h8M8 12.5h8M8 17h5" />
            </svg>
          </div>
          <h3>{{ t('home.excelTitle') }}</h3>
          <p>{{ t('home.excelDesc') }}</p>
        </a-card>

        <a-card hoverable class="home-card" :body-style="{ padding: 0 }" @click="goYaml">
          <div class="card-icon yaml-icon">
            <svg viewBox="0 0 24 24" width="40" height="40" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="3" y="3" width="18" height="18" rx="2" />
              <path d="M7 8l4 4-4 4M13 16h4" />
            </svg>
          </div>
          <h3>{{ t('home.yamlTitle') }}</h3>
          <p>{{ t('home.yamlDesc') }}</p>
        </a-card>
      </div>

      <!-- 列间箭头 / Between-column arrow -->
      <div class="column-arrow">→</div>

      <!-- ③ 执行与转换 / Execute & Convert -->
      <div class="home-column">
        <div class="section-label execute-label">{{ t('home.sectionExecute') }}</div>
        <a-card hoverable class="home-card" :body-style="{ padding: 0 }" @click="goExecutor">
          <div class="card-icon executor-icon">
            <svg viewBox="0 0 24 24" width="40" height="40" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polygon points="5,4 19,12 5,20" />
            </svg>
          </div>
          <h3>{{ t('home.executorTitle') }}</h3>
          <p>{{ t('home.executorDesc') }}</p>
        </a-card>

        <a-card hoverable class="home-card" :body-style="{ padding: 0 }" @click="goConverter">
          <div class="card-icon converter-icon">
            <svg viewBox="0 0 24 24" width="40" height="40" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="17,2 21,6 17,10" />
              <path d="M3 12V5h18" />
              <polyline points="7,22 3,18 7,14" />
              <path d="M21 12v7H3" />
            </svg>
          </div>
          <h3>{{ t('home.converterTitle') }}</h3>
          <p>{{ t('home.converterDesc') }}</p>
        </a-card>

        <!-- 诊断工具卡片 — ENABLE_DIAGNOSTICS=false 时隐藏，布局恢复 2-2-2 / Diagnostic card — hidden when ENABLE_DIAGNOSTICS=false, layout reverts to 2-2-2 -->
        <a-card v-if="ENABLE_DIAGNOSTICS" hoverable class="home-card diagnostic-card" :body-style="{ padding: 0 }" @click="goCounter">
          <div class="card-icon counter-icon">
            <svg viewBox="0 0 24 24" width="40" height="40" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
            </svg>
          </div>
          <h3>{{ t('home.counterTitle') }}</h3>
          <p>{{ t('home.counterDesc') }}</p>
        </a-card>
      </div>
    </div>

    <!-- 设置弹窗 / Settings modal -->
    <AgentSettings v-model:visible="settingsVisible" />
  </div>
</template>

<style scoped>
.home-page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 60px 20px 40px;
  background: linear-gradient(135deg, #f5f7fa 0%, #e4e8ed 100%);
}

.home-header {
  text-align: center;
  margin-bottom: 36px;
}

.home-title {
  font-size: 32px;
  font-weight: 700;
  color: #1a1a2e;
  margin: 0 0 12px 0;
}

.home-subtitle {
  font-size: 16px;
  color: #666;
  margin: 0;
}

/* ---- 3 列布局 / Three-column layout ---- */

.home-columns {
  display: flex;
  gap: 20px;
  align-items: flex-start;
  width: 100%;
  max-width: 1100px;
  justify-content: center;
}

.home-column {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
  max-width: 340px;
}

.column-arrow {
  display: flex;
  align-items: flex-start;
  font-size: 28px;
  color: #ccc;
  user-select: none;
  padding-top: 32px;
  flex-shrink: 0;
}

/* ---- Section 标签 / Section label ---- */

.section-label {
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 1px;
  margin-bottom: 4px;
  padding: 2px 10px;
  border-radius: 4px;
  display: inline-block;
  align-self: flex-start;
}

.generate-label {
  color: #4472C4;
  background: rgba(68, 114, 196, 0.1);
  border: 1px solid rgba(68, 114, 196, 0.2);
}

.edit-label {
  color: #52c41a;
  background: rgba(82, 196, 26, 0.1);
  border: 1px solid rgba(82, 196, 26, 0.2);
}

.execute-label {
  color: #fa8c16;
  background: rgba(250, 140, 22, 0.1);
  border: 1px solid rgba(250, 140, 22, 0.2);
}

/* ---- 卡片 / Cards ---- */

.home-card {
  text-align: center;
  padding: 20px 16px;
  border-radius: 12px;
  transition: transform 0.2s, box-shadow 0.2s;
  cursor: pointer;
  min-height: 220px;
  display: flex;
  flex-direction: column;
}

.home-card :deep(.ant-card-body) {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.home-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
}

.home-card h3 {
  margin: 12px 0 6px 0;
  font-size: 18px;
  font-weight: 600;
  flex-shrink: 0;
}

.home-card p {
  color: #888;
  margin: 0;
  font-size: 13px;
  line-height: 1.5;
  flex: 1;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-icon {
  flex-shrink: 0;
  margin-bottom: 4px;
  color: #4472C4;
}

.executor-icon {
  color: #fa8c16;
}

.converter-icon {
  color: #52c41a;
}

/* 诊断工具卡片图标（粉色区分）/ Diagnostic card icon (pink to distinguish) */
.counter-icon {
  color: #eb2f96;
}

/* ---- 右上角操作按钮 / Top-right action buttons ---- */

.home-actions {
  position: fixed;
  top: 16px;
  right: 24px;
  z-index: 10;
  display: flex;
  gap: 8px;
  align-items: center;
}

.action-btn {
  font-size: 18px;
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  color: #555;
  border: 1px solid #e0e0e0;
  background: rgba(255, 255, 255, 0.9);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
  transition: all 0.2s;
}

.action-btn:hover {
  color: #1890ff;
  border-color: #1890ff;
  box-shadow: 0 2px 8px rgba(24, 144, 255, 0.15);
}

/* ---- 响应式 / Responsive ---- */
@media (max-width: 600px) {
  .home-page {
    padding: 40px 16px 30px;
  }

  .home-columns {
    flex-direction: column;
    align-items: center;
    gap: 32px;
  }

  .column-arrow {
    padding-top: 0;
    transform: rotate(90deg);
  }

  .home-column {
    max-width: 360px;
    width: 100%;
  }

  .home-actions {
    right: 12px;
    top: 12px;
  }

  .action-btn {
    width: 32px;
    height: 32px;
    font-size: 16px;
  }

  .section-label {
    align-self: center;
  }
}
</style>
