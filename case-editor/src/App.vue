<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useSettingsStore } from './stores/settings'
import AppHeader from './components/layout/AppHeader.vue'
import AppSidebar from './components/layout/AppSidebar.vue'
import StatusBar from './components/layout/StatusBar.vue'
import { watch } from 'vue'

const { locale } = useI18n()
const settings = useSettingsStore()

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
      <AppSidebar class="app-sidebar" />
      <div class="app-content">
        <router-view />
      </div>
    </div>
    <StatusBar />
  </div>
</template>
