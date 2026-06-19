<script setup lang="ts">
import { computed, h, ref, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { message, Modal } from 'ant-design-vue'
import {
  EditOutlined,
  ScissorOutlined,
  CopyOutlined,
  SnippetsOutlined,
  DeleteOutlined,
  FolderOpenOutlined,
} from '@ant-design/icons-vue'
import { useYamlStore } from '../../stores/yaml-store'
import type { FileEntry } from '../../stores/yaml-store'

const { t } = useI18n()
const yamlStore = useYamlStore()

const props = defineProps<{
  files: FileEntry[]
}>()

const emit = defineEmits<{
  (e: 'select-file', path: string): void
}>()

// Expanded keys state (collapsed by default)
const expandedKeys = ref<string[]>([])

// Context menu state
const contextMenuVisible = ref(false)
const contextMenuPosition = ref({ x: 0, y: 0 })
const rightClickedNode = ref<{ key: string; isLeaf: boolean; title: string } | null>(null)

// Rename modal state
const renameModalVisible = ref(false)
const renameTargetPath = ref('')
const newNameInput = ref('')

// Convert FileEntry[] to Ant Design tree data format
const treeData = computed(() => props.files.map(toTreeNode))

const canPaste = computed(() => {
  if (!yamlStore.fileClipboard || !rightClickedNode.value) return false
  return yamlStore.fileClipboard.path !== rightClickedNode.value.key
})

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

function onRightClick(info: { event: MouseEvent; node: any }) {
  info.event.preventDefault()
  rightClickedNode.value = {
    key: info.node.key as string,
    isLeaf: info.node.isLeaf as boolean,
    title: info.node.title as string,
  }
  contextMenuPosition.value = { x: info.event.clientX, y: info.event.clientY }
  contextMenuVisible.value = true
}

function onDocumentClick() {
  contextMenuVisible.value = false
}

function handleContextMenuClick({ key }: { key: string }) {
  switch (key) {
    case 'openInExplorer': openInExplorer(); break
    case 'cut': handleCut(); break
    case 'copy': handleCopy(); break
    case 'paste': handlePaste(); break
    case 'rename': handleRename(); break
    case 'delete': handleDelete(); break
  }
}

// --- Context menu actions ---

function handleRename() {
  contextMenuVisible.value = false
  if (!rightClickedNode.value) return
  renameTargetPath.value = rightClickedNode.value.key
  newNameInput.value = rightClickedNode.value.title
  renameModalVisible.value = true
}

async function confirmRename() {
  const newName = newNameInput.value.trim()
  if (!newName || newName === rightClickedNode.value?.title) {
    renameModalVisible.value = false
    return
  }
  try {
    await yamlStore.renameFile(renameTargetPath.value, newName)
    message.success(t('yaml.renameSuccess'))
  } catch {
    message.error(t('yaml.renameFailed'))
  }
  renameModalVisible.value = false
}

function handleDelete() {
  contextMenuVisible.value = false
  if (!rightClickedNode.value) return
  Modal.confirm({
    title: t('yaml.confirmDelete'),
    content: t('yaml.confirmDeleteMsg', { name: rightClickedNode.value.title }),
    okText: t('dialog.yes'),
    cancelText: t('dialog.cancel'),
    okType: 'danger',
    onOk: async () => {
      try {
        await yamlStore.deleteFile(rightClickedNode.value!.key)
        message.success(t('yaml.deleteSuccess'))
      } catch {
        message.error(t('yaml.deleteFailed'))
      }
    },
  })
}

function handleCut() {
  contextMenuVisible.value = false
  if (!rightClickedNode.value) return
  yamlStore.cutFile(rightClickedNode.value.key)
}

function handleCopy() {
  contextMenuVisible.value = false
  if (!rightClickedNode.value) return
  yamlStore.copyFile(rightClickedNode.value.key)
}

async function handlePaste() {
  contextMenuVisible.value = false
  if (!rightClickedNode.value) return
  try {
    await yamlStore.pasteFile(rightClickedNode.value.key)
  } catch {
    message.error(t('yaml.pasteFailed'))
  }
}

async function openInExplorer() {
  contextMenuVisible.value = false
  if (!rightClickedNode.value) return
  try {
    await yamlStore.openInExplorer(rightClickedNode.value.key)
  } catch {
    message.error(t('yaml.openInExplorerFailed'))
  }
}

onMounted(() => document.addEventListener('click', onDocumentClick))
onUnmounted(() => document.removeEventListener('click', onDocumentClick))
</script>

<template>
  <div class="yaml-file-tree">
    <div class="file-tree-content">
      <a-tree
        v-if="files.length > 0"
        :tree-data="treeData"
        v-model:expanded-keys="expandedKeys"
        :show-line="true"
        :show-icon="true"
        block-node
        @select="onSelect"
        @rightClick="onRightClick"
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

    <!-- Right-click context menu -->
    <Teleport to="body">
      <div
        v-if="contextMenuVisible"
        :style="{
          position: 'fixed',
          left: contextMenuPosition.x + 'px',
          top: contextMenuPosition.y + 'px',
          zIndex: 9999,
        }"
        @click.stop
      >
        <a-menu
          @click="handleContextMenuClick"
          class="file-tree-context-menu"
        >
          <a-menu-item key="openInExplorer">
            <FolderOpenOutlined />
            <span>{{ t('yaml.openInExplorer') }}</span>
          </a-menu-item>
          <a-menu-divider />
          <a-menu-item key="cut">
            <ScissorOutlined />
            <span>{{ t('yaml.cut') }}</span>
          </a-menu-item>
          <a-menu-item key="copy">
            <CopyOutlined />
            <span>{{ t('yaml.copy') }}</span>
          </a-menu-item>
          <a-menu-item key="paste" :disabled="!canPaste">
            <SnippetsOutlined />
            <span>{{ t('yaml.paste') }}</span>
          </a-menu-item>
          <a-menu-divider />
          <a-menu-item key="rename">
            <EditOutlined />
            <span>{{ t('yaml.rename') }}</span>
          </a-menu-item>
          <a-menu-item key="delete" danger>
            <DeleteOutlined />
            <span>{{ t('yaml.delete') }}</span>
          </a-menu-item>
        </a-menu>
      </div>
    </Teleport>

    <!-- Rename modal -->
    <a-modal
      v-model:open="renameModalVisible"
      :title="t('yaml.rename')"
      @ok="confirmRename"
      :okText="t('dialog.confirm')"
      :cancelText="t('dialog.cancel')"
    >
      <a-input
        v-model:value="newNameInput"
        :placeholder="t('yaml.renamePlaceholder')"
        @pressEnter="confirmRename"
        autofocus
      />
    </a-modal>
  </div>
</template>

<style scoped>
.yaml-file-tree {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
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

<style>
.file-tree-context-menu {
  border: 1px solid #e8e8e8;
  border-radius: 6px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.12);
  min-width: 200px;
}
</style>
