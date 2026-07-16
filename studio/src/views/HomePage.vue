<script setup lang="ts">
// HomePage — 首页，6 个功能入口卡片，分 3 组（生成 → 编辑 → 执行）。
// Homepage with 6 feature entry cards in 3 groups (Generate → Edit → Execute).
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useSettingsStore } from '../stores/settings'

const router = useRouter()
const { t } = useI18n()
const settings = useSettingsStore()

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

function handleLanguageChange(lang: string) {
  settings.setLanguage(lang as 'zh-CN' | 'en-US')
}
</script>

<template>
  <div class="home-page">
    <div class="home-lang-switch">
      <a-select
        :value="settings.language"
        size="small"
        style="width: 90px"
        @change="handleLanguageChange"
      >
        <a-select-option value="zh-CN">中文</a-select-option>
        <a-select-option value="en-US">English</a-select-option>
      </a-select>
    </div>

    <div class="home-header">
      <h1 class="home-title">{{ t('home.title') }}</h1>
      <p class="home-subtitle">{{ t('home.subtitle') }}</p>
    </div>

    <!-- ① 用例生成 / Generate -->
    <div class="home-section">
      <div class="section-label generate-label">{{ t('home.sectionGenerate') }}</div>
      <div class="section-cards">
        <a-card hoverable class="home-card" @click="goAgent">
          <div class="card-icon agent-icon">
            <svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.5">
              <circle cx="12" cy="12" r="9" />
              <path d="M12 7v5l4 2" />
              <path d="M8 14c-1-2 0-5 4-5s5 3 4 5" />
            </svg>
          </div>
          <h3>{{ t('home.agentTitle') }}</h3>
          <p>{{ t('home.agentDesc') }}</p>
          <a-button type="primary" size="large">{{ t('home.open') }}</a-button>
        </a-card>

        <div class="card-arrow">▶</div>

        <a-card hoverable class="home-card" @click="goPlanAnnotator">
          <div class="card-icon annotator-icon">
            <svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M12 20h9" />
              <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
            </svg>
          </div>
          <h3>{{ t('home.annotatorTitle') }}</h3>
          <p>{{ t('home.annotatorDesc') }}</p>
          <a-button type="primary" size="large">{{ t('home.open') }}</a-button>
        </a-card>
      </div>
    </div>

    <div class="section-down-arrow">↓</div>

    <!-- ② 用例编辑 / Edit -->
    <div class="home-section">
      <div class="section-label edit-label">{{ t('home.sectionEdit') }}</div>
      <div class="section-cards">
        <a-card hoverable class="home-card" @click="goExcel">
          <div class="card-icon excel-icon">
            <svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.5">
              <rect x="3" y="3" width="18" height="18" rx="2" />
              <path d="M8 7h8M8 12h8M8 17h5" />
            </svg>
          </div>
          <h3>{{ t('home.excelTitle') }}</h3>
          <p>{{ t('home.excelDesc') }}</p>
          <a-button type="primary" size="large">{{ t('home.open') }}</a-button>
        </a-card>

        <div class="card-arrow">▶</div>

        <a-card hoverable class="home-card" @click="goYaml">
          <div class="card-icon yaml-icon">
            <svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.5">
              <rect x="3" y="3" width="18" height="18" rx="2" />
              <path d="M7 8l4 4-4 4M12 16h5" />
            </svg>
          </div>
          <h3>{{ t('home.yamlTitle') }}</h3>
          <p>{{ t('home.yamlDesc') }}</p>
          <a-button type="primary" size="large">{{ t('home.open') }}</a-button>
        </a-card>
      </div>
    </div>

    <div class="section-down-arrow">↓</div>

    <!-- ③ 执行与转换 / Execute & Convert -->
    <div class="home-section">
      <div class="section-label execute-label">{{ t('home.sectionExecute') }}</div>
      <div class="section-cards">
        <a-card hoverable class="home-card" @click="goExecutor">
          <div class="card-icon executor-icon">
            <svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.5">
              <polygon points="5,3 19,12 5,21" />
            </svg>
          </div>
          <h3>{{ t('home.executorTitle') }}</h3>
          <p>{{ t('home.executorDesc') }}</p>
          <a-button type="primary" size="large">{{ t('home.open') }}</a-button>
        </a-card>

        <div class="card-arrow">▶</div>

        <a-card hoverable class="home-card" @click="goConverter">
          <div class="card-icon converter-icon">
            <svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.5">
              <polyline points="17,1 21,5 17,9" />
              <path d="M3 12V5h18" />
              <polyline points="7,23 3,19 7,15" />
              <path d="M21 12v7H3" />
            </svg>
          </div>
          <h3>{{ t('home.converterTitle') }}</h3>
          <p>{{ t('home.converterDesc') }}</p>
          <a-button type="primary" size="large">{{ t('home.open') }}</a-button>
        </a-card>
      </div>
    </div>
  </div>
</template>

<style scoped>
.home-page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #f5f7fa 0%, #e4e8ed 100%);
  padding: 40px 20px;
}

.home-header {
  text-align: center;
  margin-bottom: 48px;
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

/* ---- Section / 分组 ---- */

.home-section {
  width: 100%;
  max-width: 820px;
  margin-bottom: 8px;
}

.section-label {
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 1px;
  margin-bottom: 12px;
  padding: 2px 10px;
  border-radius: 4px;
  display: inline-block;
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

.section-cards {
  display: flex;
  gap: 16px;
  align-items: center;
  flex-wrap: wrap;
}

.section-down-arrow {
  font-size: 24px;
  color: #bbb;
  margin: 4px 0;
  user-select: none;
}

.card-arrow {
  font-size: 20px;
  color: #ccc;
  flex-shrink: 0;
  user-select: none;
}

.home-card {
  flex: 1;
  min-width: 240px;
  max-width: 320px;
  text-align: center;
  padding: 32px 24px;
  border-radius: 12px;
  transition: transform 0.2s, box-shadow 0.2s;
  cursor: pointer;
}

.home-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
}

.home-card h3 {
  margin: 16px 0 8px 0;
  font-size: 20px;
  font-weight: 600;
}

.home-card p {
  color: #888;
  margin: 0 0 20px 0;
  font-size: 14px;
  line-height: 1.5;
}

.home-lang-switch {
  position: fixed;
  top: 16px;
  right: 24px;
  z-index: 10;
}

.card-icon {
  margin-bottom: 8px;
  color: #4472C4;
}

.executor-icon {
  color: #fa8c16;
}

.converter-icon {
  color: #52c41a;
}

/* ---- Responsive / 响应式 ---- */
@media (max-width: 600px) {
  .section-cards {
    flex-direction: column;
    align-items: center;
  }
  .card-arrow {
    transform: rotate(90deg);
  }
  .home-card {
    max-width: 360px;
    width: 100%;
  }
}
</style>
