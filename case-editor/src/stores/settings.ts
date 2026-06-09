import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Language } from '../types/editor'

export const useSettingsStore = defineStore('settings', () => {
  const language = ref<Language>((localStorage.getItem('case-editor-lang') as Language) || 'zh-CN')

  function setLanguage(lang: Language) {
    language.value = lang
    localStorage.setItem('case-editor-lang', lang)
  }

  return { language, setLanguage }
})
