<script setup lang="ts">
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useSettingsStore } from './stores/settings'
import { useWorkbookStore } from './stores/workbook'
import AppHeader from './components/layout/AppHeader.vue'
import AppSidebar from './components/layout/AppSidebar.vue'
import StatusBar from './components/layout/StatusBar.vue'
import { watch, computed } from 'vue'

const route = useRoute()
const { t, locale } = useI18n()
const settings = useSettingsStore()
const workbook = useWorkbookStore()

const isHome = computed(() => route.name === 'home')

watch(
  () => settings.language,
  (lang) => {
    locale.value = lang
  },
  { immediate: true }
)
</script>

<template>
  <!-- Home page: no chrome -->
  <div v-if="isHome" class="app-layout home-layout">
    <router-view />
  </div>

  <!-- Editor pages: full chrome -->
  <div v-else class="app-layout">
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
