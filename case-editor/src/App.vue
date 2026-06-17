<script setup lang="ts">
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useSettingsStore } from './stores/settings'
import { useWorkbookStore } from './stores/workbook'
import { useYamlStore } from './stores/yaml-store'
import AppHeader from './components/layout/AppHeader.vue'
import AppSidebar from './components/layout/AppSidebar.vue'
import StatusBar from './components/layout/StatusBar.vue'
import { watch, computed, onMounted, onUnmounted } from 'vue'

const route = useRoute()
const { t, locale } = useI18n()
const settings = useSettingsStore()
const workbook = useWorkbookStore()
const yamlStore = useYamlStore()

const isHome = computed(() => route.name === 'home')
const isAnnotator = computed(() => route.name === 'plan-annotator')
const isYamlMode = computed(() => route.name === 'yaml-editor')

watch(
  () => settings.language,
  (lang) => {
    locale.value = lang
  },
  { immediate: true }
)

function onBeforeUnload(e: BeforeUnloadEvent) {
  if (yamlStore.hasUnsavedTabs || workbook.modified) {
    e.preventDefault()
    e.returnValue = ''
  }
}

onMounted(() => window.addEventListener('beforeunload', onBeforeUnload))
onUnmounted(() => window.removeEventListener('beforeunload', onBeforeUnload))
</script>

<template>
  <!-- Home page: no chrome -->
  <div v-if="isHome" class="app-layout home-layout">
    <router-view />
  </div>

  <!-- Annotator page: no chrome, standalone -->
  <div v-else-if="isAnnotator" class="app-layout annotator-layout">
    <router-view />
  </div>

  <!-- Editor pages: full chrome -->
  <div v-else class="app-layout">
    <AppHeader />
    <div class="app-main">
      <div v-if="workbook.loading" class="loading-overlay">
        <a-spin size="large" :tip="t('loading')" />
      </div>
      <AppSidebar v-if="!isYamlMode" class="app-sidebar" />
      <div class="app-content">
        <router-view />
      </div>
    </div>
    <StatusBar />
  </div>
</template>
