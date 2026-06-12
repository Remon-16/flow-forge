<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useYamlStore } from '../../stores/yaml-store'
import { stringifyYaml, parseYaml } from '../../utils/yaml-parser'

const { t } = useI18n()
const yamlStore = useYamlStore()

const isOpen = ref(false)
const editMode = ref(true) // default to editable mode
const editText = ref('')

let debounceTimer: ReturnType<typeof setTimeout> | null = null

const yamlText = computed(() => {
  if (!yamlStore.currentCase) return ''
  try {
    return stringifyYaml(yamlStore.currentCase)
  } catch (err) {
    console.error('Failed to stringify YAML:', err)
    return '# Error: Failed to generate YAML'
  }
})

// Sync when current case changes (form -> raw)
watch(
  () => yamlStore.currentCase,
  () => {
    if (editMode.value) {
      editText.value = yamlText.value
    }
  },
  { immediate: true }
)

// Debounced sync from raw text -> form
watch(editText, (newText) => {
  if (!editMode.value) return
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    try {
      const parsed = parseYaml(newText)
      if (parsed && parsed.case_type === yamlStore.currentCase?.case_type) {
        yamlStore.currentCase = parsed
        yamlStore.markModified()
      }
    } catch {
      // Ignore parse errors during typing
    }
  }, 500)
})

function togglePanel() {
  isOpen.value = !isOpen.value
  if (isOpen.value) {
    editText.value = yamlText.value
    editMode.value = true
  }
}

function toggleEditMode() {
  if (editMode.value) {
    // Switching from edit back to preview
    editMode.value = false
  } else {
    // Switching to edit: copy current YAML text
    editText.value = yamlText.value
    editMode.value = true
  }
}

function onTextBlur() {
  // Try to apply changes immediately when leaving text area
  if (!editMode.value) return
  if (debounceTimer) {
    clearTimeout(debounceTimer)
    debounceTimer = null
  }
  try {
    const parsed = parseYaml(editText.value)
    if (parsed && parsed.case_type === yamlStore.currentCase?.case_type) {
      yamlStore.currentCase = parsed
      yamlStore.markModified()
    }
  } catch {
    // Ignore parse errors on blur
  }
}
</script>

<template>
  <div class="yaml-raw-view" :class="{ open: isOpen }">
    <div class="raw-toggle" @click="togglePanel" :title="t('yaml.rawView')">
      <span class="toggle-label">
        <span v-if="!isOpen" class="toggle-hint">YAML</span>
        <span v-else>{{ t('yaml.rawView') }}</span>
        <span class="toggle-arrow">{{ isOpen ? '▶' : '◀' }}</span>
      </span>
    </div>

    <div v-if="isOpen" class="raw-content">
      <div class="raw-toolbar">
        <span class="raw-title">{{ t('yaml.rawView') }}</span>
        <a-button size="small" type="text" @click="toggleEditMode">
          {{ editMode ? t('yaml.formView') : t('yaml.splitView') }}
        </a-button>
      </div>

      <!-- Editable textarea (default) -->
      <a-textarea
        v-if="editMode"
        v-model:value="editText"
        class="raw-editor"
        :auto-size="false"
        @blur="onTextBlur"
      />

      <!-- Read-only preview -->
      <pre v-else class="raw-preview">{{ yamlText }}</pre>
    </div>
  </div>
</template>

<style scoped>
.yaml-raw-view {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #1e1e1e;
  color: #d4d4d4;
  border-left: 1px solid #333;
  transition: width 0.2s;
  width: 40px;
  min-width: 40px;
  overflow: hidden;
}

.yaml-raw-view.open {
  width: 320px;
  min-width: 200px;
}

.raw-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 8px 4px;
  cursor: pointer;
  user-select: none;
  writing-mode: vertical-rl;
  text-orientation: mixed;
  flex-shrink: 0;
}

.yaml-raw-view.open .raw-toggle {
  writing-mode: horizontal-tb;
  justify-content: flex-start;
}

.toggle-label {
  font-size: 12px;
  color: #999;
}

.toggle-hint {
  font-size: 11px;
  letter-spacing: 2px;
}

.toggle-arrow {
  font-size: 10px;
}

.raw-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.raw-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 8px;
  border-bottom: 1px solid #333;
}

.raw-title {
  font-size: 12px;
  font-weight: 600;
  color: #999;
}

.raw-preview {
  flex: 1;
  margin: 0;
  padding: 12px;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.5;
  overflow: auto;
  white-space: pre;
  color: #d4d4d4;
}

.raw-editor {
  flex: 1;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace !important;
  font-size: 12px !important;
  line-height: 1.5;
  background: #1e1e1e;
  color: #d4d4d4;
  border: none;
  resize: none;
}

.raw-editor :deep(textarea) {
  background: #1e1e1e !important;
  color: #d4d4d4 !important;
  border: none !important;
  height: 100% !important;
}
</style>
