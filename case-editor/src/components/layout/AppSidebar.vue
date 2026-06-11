<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useWorkbookStore } from '../../stores/workbook'
import { useEditorStore } from '../../stores/editor'

const route = useRoute()
const { t } = useI18n()
const workbook = useWorkbookStore()
const editor = useEditorStore()

interface MenuItem {
  key: string
  label: string
  icon: string
  index: number
}

const menuItems = computed<MenuItem[]>(() => {
  const items: MenuItem[] = [
    {
      key: 'apiDef',
      label: t('table.sheetApiDef'),
      icon: '📋',
      index: -1,
    },
    {
      key: 'singleCase',
      label: t('table.sheetSingleCase'),
      icon: '📝',
      index: 0,
    },
  ]

  workbook.bizFlows.forEach((flow, i) => {
    items.push({
      key: `biz_${i}`,
      label: flow.sheetName || `BizFlow ${i + 1}`,
      icon: '🔗',
      index: i + 1,
    })
  })

  return items
})

function onSelect(key: string) {
  const item = menuItems.value.find((m) => m.key === key)
  if (item) {
    editor.setActiveSheet(item.index)
  }
}

function onAddBizFlow() {
  const name = `业务链路 ${workbook.bizFlows.length + 1}`
  workbook.addBizFlow(name)
}

const selectedKey = computed(() => {
  if (editor.activeSheetIndex === -1) return ['apiDef']
  if (editor.activeSheetIndex === 0) return ['singleCase']
  return [`biz_${editor.activeSheetIndex - 1}`]
})

// Hide sidebar in YAML mode (YamlFileTree replaces it)
const isYamlMode = computed(() => route.name === 'yaml-editor')
</script>

<template>
  <div v-if="isYamlMode" class="sidebar-hidden" />
  <div v-else style="padding: 8px;">
    <a-menu
      mode="inline"
      :selectedKeys="selectedKey"
      style="border-inline-end: none;"
      @click="({ key }: { key: string }) => onSelect(key)"
    >
      <a-menu-item v-for="item in menuItems" :key="item.key">
        <template #icon>
          <span>{{ item.icon }}</span>
        </template>
        <span style="font-size: 13px;">{{ item.label }}</span>
      </a-menu-item>
    </a-menu>

    <a-divider style="margin: 8px 0;" />

    <a-button size="small" block type="dashed" @click="onAddBizFlow">
      + {{ t('table.addBizFlow') }}
    </a-button>
  </div>
</template>

<style scoped>
.sidebar-hidden {
  width: 0;
  overflow: hidden;
}
</style>
