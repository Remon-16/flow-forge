<script setup lang="ts">
// EditorToolbar — 编辑器右上角工具栏，split button 运行/转换按钮。
// Editor toolbar with split button for run and convert actions.
import { ref, computed, h, type VNode } from 'vue'
import { useI18n } from 'vue-i18n'
import { Dropdown, Menu, MenuItem, MenuDivider } from 'ant-design-vue'

const { t } = useI18n()

// ============================================================================
// Props & Emits
// ============================================================================

const props = defineProps<{
  /** 编辑器类型 / Editor type */
  editorType: 'excel' | 'yaml'
  /** 当前文件路径（用于记忆默认动作） / Current file path (for remembering default action) */
  filePath?: string
}>()

const emit = defineEmits<{
  /** 执行动作 / Run actions */
  runAll: []
  runSingle: []
  runBiz: []
  runSelect: []
  /** 转换动作 / Convert actions */
  convertAll: []
  convertSingle: []
  convertBiz: []
  convertSelect: []
  /** 编辑参数 / Edit params */
  editRunParams: []
  editConvertParams: []
}>()

// ============================================================================
// Default action memory / 默认动作记忆
// ============================================================================

type RunAction = 'all' | 'single' | 'biz' | 'select'
type ConvertAction = 'all' | 'single' | 'biz' | 'select'

const defaultRunAction = ref<RunAction>('all')
const defaultConvertAction = ref<ConvertAction>('all')

// Simple per-file memory (not persisted across sessions)
const memoryKey = computed(() => `${props.editorType}:${props.filePath || ''}`)

// ============================================================================
// Menu items / 菜单项
// ============================================================================

const runMenuItems = computed(() => [
  { key: 'all', label: t('editor.toolbar.runAll'), icon: '▶' },
  { key: 'single', label: t('editor.toolbar.runSingle'), icon: '▶' },
  { key: 'biz', label: t('editor.toolbar.runBiz'), icon: '▶' },
  { key: 'select', label: t('editor.toolbar.runSelect'), icon: '▶' },
  { type: 'divider' as const },
  { key: 'editRunParams', label: t('editor.toolbar.editRunParams'), icon: '⚙' },
])

const convertMenuItems = computed(() => [
  { key: 'all', label: t('editor.toolbar.convertAll'), icon: '⟳' },
  { key: 'single', label: t('editor.toolbar.convertSingle'), icon: '⟳' },
  { key: 'biz', label: t('editor.toolbar.convertBiz'), icon: '⟳' },
  { key: 'select', label: t('editor.toolbar.convertSelect'), icon: '⟳' },
  { type: 'divider' as const },
  { key: 'editConvertParams', label: t('editor.toolbar.editConvertParams'), icon: '⚙' },
])

// ============================================================================
// Action handlers / 动作处理
// ============================================================================

function getRunActionLabel(action: RunAction): string {
  const item = runMenuItems.value.find(i => i.key === action)
  return item?.label || ''
}

function getConvertActionLabel(action: ConvertAction): string {
  const item = convertMenuItems.value.find(i => i.key === action)
  return item?.label || ''
}

function handleRunMenuClick(info: { key: string }) {
  const key = info.key
  if (key === 'editRunParams') {
    emit('editRunParams')
    return
  }
  defaultRunAction.value = key as RunAction
  switch (key) {
    case 'all': emit('runAll'); break
    case 'single': emit('runSingle'); break
    case 'biz': emit('runBiz'); break
    case 'select': emit('runSelect'); break
  }
}

function handleConvertMenuClick(info: { key: string }) {
  const key = info.key
  if (key === 'editConvertParams') {
    emit('editConvertParams')
    return
  }
  defaultConvertAction.value = key as ConvertAction
  switch (key) {
    case 'all': emit('convertAll'); break
    case 'single': emit('convertSingle'); break
    case 'biz': emit('convertBiz'); break
    case 'select': emit('convertSelect'); break
  }
}

function handleRunDefault() {
  switch (defaultRunAction.value) {
    case 'all': emit('runAll'); break
    case 'single': emit('runSingle'); break
    case 'biz': emit('runBiz'); break
    case 'select': emit('runSelect'); break
  }
}

function handleConvertDefault() {
  switch (defaultConvertAction.value) {
    case 'all': emit('convertAll'); break
    case 'single': emit('convertSingle'); break
    case 'biz': emit('convertBiz'); break
    case 'select': emit('convertSelect'); break
  }
}
</script>

<template>
  <div class="editor-toolbar">
    <!-- Run split button / 运行按钮组 -->
    <a-dropdown :trigger="['click']">
      <a-button-group>
        <a-button size="small" type="text" @click="handleRunDefault" class="toolbar-btn">
          ▶
        </a-button>
        <a-button size="small" type="text" class="toolbar-drop-arrow"
          @click.stop
        >
          <span class="arrow">▼</span>
        </a-button>
      </a-button-group>
      <template #overlay>
        <a-menu @click="handleRunMenuClick">
          <a-menu-item
            v-for="item in runMenuItems.filter(i => i.type !== 'divider' && i.key !== 'editRunParams')"
            :key="item.key"
          >
            <span :class="{ 'active-action': item.key === defaultRunAction }">
              {{ item.label }}
            </span>
          </a-menu-item>
          <a-menu-divider />
          <a-menu-item key="editRunParams">
            ⚙ {{ t('editor.toolbar.editRunParams') }}
          </a-menu-item>
        </a-menu>
      </template>
    </a-dropdown>

    <!-- Convert split button / 转换按钮组 -->
    <a-dropdown :trigger="['click']" style="margin-left: 8px">
      <a-button-group>
        <a-button size="small" type="text" @click="handleConvertDefault" class="toolbar-btn">
          ⟳
        </a-button>
        <a-button size="small" type="text" class="toolbar-drop-arrow"
          @click.stop
        >
          <span class="arrow">▼</span>
        </a-button>
      </a-button-group>
      <template #overlay>
        <a-menu @click="handleConvertMenuClick">
          <a-menu-item
            v-for="item in convertMenuItems.filter(i => i.type !== 'divider' && i.key !== 'editConvertParams')"
            :key="item.key"
          >
            <span :class="{ 'active-action': item.key === defaultConvertAction }">
              {{ item.label }}
            </span>
          </a-menu-item>
          <a-menu-divider />
          <a-menu-item key="editConvertParams">
            ⚙ {{ t('editor.toolbar.editConvertParams') }}
          </a-menu-item>
        </a-menu>
      </template>
    </a-dropdown>
  </div>
</template>

<style scoped>
.editor-toolbar {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 2px 8px;
}
.toolbar-btn {
  font-size: 16px;
  padding: 0 8px;
  height: 28px;
  line-height: 1;
  color: #555;
}
.toolbar-btn:hover {
  color: #1890ff;
  background: rgba(24, 144, 255, 0.06);
}
.toolbar-drop-arrow {
  padding: 0 4px;
  min-width: 20px;
  height: 28px;
}
.arrow {
  font-size: 8px;
  color: #999;
}
.active-action {
  font-weight: 600;
  color: #1890ff;
}
</style>
