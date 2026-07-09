import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Language } from '../types/editor'

const ZOOM_MIN = 0.5
const ZOOM_MAX = 2.0
const ZOOM_STEP = 0.1

export const useSettingsStore = defineStore('settings', () => {
  const language = ref<Language>((localStorage.getItem('studio-lang') as Language) || 'zh-CN')
  const zoom = ref<number>(parseFloat(localStorage.getItem('studio-zoom') || '1.0'))
  const showLineNumbers = ref<boolean>(localStorage.getItem('studio-line-numbers') === 'true')

  function setLanguage(lang: Language) {
    language.value = lang
    localStorage.setItem('studio-lang', lang)
  }

  function setZoom(value: number) {
    zoom.value = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, Math.round(value * 10) / 10))
    localStorage.setItem('studio-zoom', String(zoom.value))
  }
  function zoomIn() { setZoom(zoom.value + ZOOM_STEP) }
  function zoomOut() { setZoom(zoom.value - ZOOM_STEP) }
  function zoomReset() { setZoom(1.0) }

  function setLineNumbers(value: boolean) {
    showLineNumbers.value = value
    localStorage.setItem('studio-line-numbers', String(value))
  }
  function toggleLineNumbers() { setLineNumbers(!showLineNumbers.value) }

  const zoomPercent = computed(() => Math.round(zoom.value * 100) + '%')

  return {
    language, zoom, zoomPercent, showLineNumbers,
    setLanguage, setZoom, zoomIn, zoomOut, zoomReset,
    setLineNumbers, toggleLineNumbers,
  }
})
