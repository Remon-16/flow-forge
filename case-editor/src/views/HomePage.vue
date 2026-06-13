<script setup lang="ts">
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

    <div class="home-cards">
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

.home-cards {
  display: flex;
  gap: 32px;
  max-width: 800px;
  width: 100%;
  justify-content: center;
  flex-wrap: wrap;
}

.home-card {
  flex: 1;
  min-width: 280px;
  max-width: 360px;
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
</style>
