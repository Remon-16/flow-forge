<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useSettingsStore } from './stores/settings'
import { useWorkbookStore } from './stores/workbook'
import AppHeader from './components/layout/AppHeader.vue'
import AppSidebar from './components/layout/AppSidebar.vue'
import StatusBar from './components/layout/StatusBar.vue'
import { watch } from 'vue'

const { t, locale } = useI18n()
const settings = useSettingsStore()
const workbook = useWorkbookStore()

watch(
  () => settings.language,
  (lang) => {
    locale.value = lang
  },
  { immediate: true }
)
</script>

<template>
  <div class="app-layout">
    <AppHeader />
    <div class="app-main">
      <div v-if="workbook.loading" class="loading-overlay">
        <a-spin size="large" :tip="t('loading')" />
      </div>
      <AppSidebar class="app-sidebar" />
      <div class="app-content">
        <router-view />
      </div>
    </div>
    <StatusBar />
  </div>
</template>
