<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useYamlStore } from '../stores/yaml-store'
import YamlFileTree from '../components/yaml-editor/YamlFileTree.vue'
import YamlTabBar from '../components/yaml-editor/YamlTabBar.vue'
import SingleCaseForm from '../components/yaml-editor/SingleCaseForm.vue'
import BizFlowForm from '../components/yaml-editor/BizFlowForm.vue'
import YamlRawView from '../components/yaml-editor/YamlRawView.vue'

const { t } = useI18n()
const yamlStore = useYamlStore()

function onSelectFile(filePath: string) {
  yamlStore.openFile(filePath)
}

function onTabSwitch(index: number) {
  yamlStore.switchTab(index)
}

// Close confirm modal
const closeConfirmVisible = ref(false)
const closeConfirmIndex = ref(-1)

function onTabClose(index: number) {
  const tab = yamlStore.openTabs[index]
  if (tab && tab.modified) {
    closeConfirmIndex.value = index
    closeConfirmVisible.value = true
    yamlStore.switchTab(index)
  } else {
    yamlStore.closeTab(index)
  }
}

async function handleSaveAndClose() {
  await yamlStore.save()
  yamlStore.closeTab(closeConfirmIndex.value)
  closeConfirmVisible.value = false
}

function handleDiscardAndClose() {
  yamlStore.closeTab(closeConfirmIndex.value)
  closeConfirmVisible.value = false
}

function handleCancelClose() {
  closeConfirmVisible.value = false
}
</script>

<template>
  <div class="yaml-editor-view">
    <!-- Left: File tree -->
    <div class="yaml-left-panel">
      <YamlFileTree
        :files="yamlStore.fileTree"
        @select-file="onSelectFile"
      />
    </div>

    <!-- Center: Tab bar + Form editor -->
    <div class="yaml-center-panel">
      <!-- Tab bar -->
      <YamlTabBar
        :tabs="yamlStore.openTabs"
        :active-index="yamlStore.activeTabIndex"
        @switch="onTabSwitch"
        @close="onTabClose"
      />

      <div class="yaml-center-content">
        <div v-if="yamlStore.loading" class="yaml-loading">
          <a-spin size="large" :tip="t('loading')" />
        </div>

        <div v-else-if="!yamlStore.currentCase" class="yaml-empty">
          <div class="empty-icon">
            <svg viewBox="0 0 24 24" width="64" height="64" fill="none" stroke="#ccc" stroke-width="1">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
              <line x1="16" y1="13" x2="8" y2="13"/>
              <line x1="16" y1="17" x2="8" y2="17"/>
            </svg>
          </div>
          <p>{{ t('yaml.noFileSelected') }}</p>
          <p class="sub-hint">{{ t('yaml.selectFileHint') }}</p>
        </div>

        <!-- Single case form -->
        <SingleCaseForm v-else-if="yamlStore.isSingleCase" />

        <!-- Biz flow form -->
        <BizFlowForm v-else-if="yamlStore.isBizCase" />
      </div>
    </div>

    <!-- Right: Raw YAML view -->
    <YamlRawView />

    <!-- Close confirm modal -->
    <a-modal
      v-model:open="closeConfirmVisible"
      :title="t('validator.unsavedTitle')"
      @cancel="handleCancelClose"
    >
      <p>{{ t('yaml.unsavedPrompt') }}</p>
      <template #footer>
        <a-button @click="handleCancelClose">{{ t('dialog.cancel') }}</a-button>
        <a-button @click="handleDiscardAndClose">{{ t('yaml.discardChanges') }}</a-button>
        <a-button type="primary" @click="handleSaveAndClose">{{ t('yaml.saveAndClose') }}</a-button>
      </template>
    </a-modal>
  </div>
</template>

<style scoped>
.yaml-editor-view {
  height: 100%;
  display: flex;
  overflow: hidden;
}

.yaml-left-panel {
  width: 250px;
  min-width: 180px;
  flex-shrink: 0;
}

.yaml-center-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
}

.yaml-center-content {
  flex: 1;
  overflow: auto;
}

.yaml-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}

.yaml-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #999;
  font-size: 16px;
  gap: 8px;
}

.sub-hint {
  font-size: 13px;
  color: #bbb;
}
</style>
