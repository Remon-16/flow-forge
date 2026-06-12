<script setup lang="ts">
import { computed, h } from 'vue'
import { useI18n } from 'vue-i18n'
import type { FileEntry } from '../../stores/yaml-store'

const { t } = useI18n()

const props = defineProps<{
  files: FileEntry[]
}>()

const emit = defineEmits<{
  (e: 'select-file', path: string): void
}>()

// Convert FileEntry[] to Ant Design tree data format
const treeData = computed(() => props.files.map(toTreeNode))

function toTreeNode(entry: FileEntry): any {
  const isYaml = /\.ya?ml$/i.test(entry.name)
  const node: any = {
    title: entry.name,
    key: entry.path,
    isLeaf: !entry.isDirectory,
    selectable: isYaml,
    icon: entry.isDirectory
      ? () => h('span', { style: 'font-size:14px;' }, '📁')
      : () => h('span', { style: 'font-size:14px;' }, '📄'),
  }

  if (entry.children && entry.children.length > 0) {
    node.children = entry.children.map(toTreeNode)
  }

  return node
}

function onSelect(_selectedKeys: string[], info: { node: any }) {
  const key = info.node.key as string
  if (/\.ya?ml$/i.test(key)) {
    emit('select-file', key)
  }
}

function onContextMenu(e: MouseEvent) {
  // Future: context menu for new file/folder/delete/rename
  e.preventDefault()
}
</script>

<template>
  <div class="yaml-file-tree">
    <div class="file-tree-content" @contextmenu="onContextMenu">
      <a-tree
        v-if="files.length > 0"
        :tree-data="treeData"
        :default-expand-all="false"
        :show-line="true"
        :show-icon="true"
        block-node
        @select="onSelect"
      >
        <template #title="{ title }">
          <span class="tree-node-title">{{ title }}</span>
        </template>
      </a-tree>

      <div v-else class="tree-empty">
        <p>{{ t('yaml.noFileSelected') }}</p>
        <p class="tree-hint">{{ t('yaml.selectFileHintUpdated') }}</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.yaml-file-tree {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #fafafa;
  border-right: 1px solid #e8e8e8;
}

.file-tree-content {
  flex: 1;
  overflow: auto;
  padding: 8px 4px;
}

.tree-empty {
  padding: 16px;
  text-align: center;
  color: #999;
  font-size: 13px;
}

.tree-hint {
  font-size: 11px;
  color: #bbb;
}

.tree-node-title {
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
