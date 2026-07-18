<script setup lang="ts">
// EditorToolbar — 编辑器右上角工具栏，独立下拉选择 + 动作按钮 + 参数编辑。
// Editor toolbar with independent dropdown selectors, action buttons, and param edit.
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { PlayCircleOutlined, RetweetOutlined, MoreOutlined } from '@ant-design/icons-vue'

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

// ============================================================================
// Action items (without icons — icons are rendered as separate components)
// ============================================================================

const runActionItems = computed(() => [
  { key: 'all', label: t('editor.toolbar.runAll') },
  { key: 'single', label: t('editor.toolbar.runSingle') },
  { key: 'biz', label: t('editor.toolbar.runBiz') },
  { key: 'select', label: t('editor.toolbar.runSelect') },
])

const convertActionItems = computed(() => [
  { key: 'all', label: t('editor.toolbar.convertAll') },
  { key: 'single', label: t('editor.toolbar.convertSingle') },
  { key: 'biz', label: t('editor.toolbar.convertBiz') },
  { key: 'select', label: t('editor.toolbar.convertSelect') },
])

// ============================================================================
// Action handlers / 动作处理
// ============================================================================

function getRunActionLabel(action: RunAction): string {
  const item = runActionItems.value.find(i => i.key === action)
  return item?.label || ''
}

function getConvertActionLabel(action: ConvertAction): string {
  const item = convertActionItems.value.find(i => i.key === action)
  return item?.label || ''
}

function handleRunMenuClick(info: { key: string }) {
  const key = info.key
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
    <!-- ====== 执行组 / Run Group ====== -->
    <a-dropdown :trigger="['click']">
      <a-button size="small" class="toolbar-select-btn">
        {{ getRunActionLabel(defaultRunAction) }}
        <span class="arrow">▼</span>
      </a-button>
      <template #overlay>
        <a-menu @click="handleRunMenuClick">
          <a-menu-item
            v-for="item in runActionItems"
            :key="item.key"
          >
            <span :class="{ 'active-action': item.key === defaultRunAction }">
              {{ item.label }}
            </span>
          </a-menu-item>
        </a-menu>
      </template>
    </a-dropdown>

    <a-button size="small" type="text" class="toolbar-icon-btn" @click="handleRunDefault" :title="t('editor.toolbar.runAll')">
      <PlayCircleOutlined />
    </a-button>

    <a-button size="small" type="text" class="toolbar-icon-btn" @click="emit('editRunParams')" :title="t('editor.toolbar.editRunParams')">
      <MoreOutlined />
    </a-button>

    <!-- 分隔 / Separator -->
    <div class="toolbar-separator"></div>

    <!-- ====== 转换组 / Convert Group ====== -->
    <a-dropdown :trigger="['click']">
      <a-button size="small" class="toolbar-select-btn">
        {{ getConvertActionLabel(defaultConvertAction) }}
        <span class="arrow">▼</span>
      </a-button>
      <template #overlay>
        <a-menu @click="handleConvertMenuClick">
          <a-menu-item
            v-for="item in convertActionItems"
            :key="item.key"
          >
            <span :class="{ 'active-action': item.key === defaultConvertAction }">
              {{ item.label }}
            </span>
          </a-menu-item>
        </a-menu>
      </template>
    </a-dropdown>

    <a-button size="small" type="text" class="toolbar-icon-btn" @click="handleConvertDefault" :title="t('editor.toolbar.convertAll')">
      <RetweetOutlined />
    </a-button>

    <a-button size="small" type="text" class="toolbar-icon-btn" @click="emit('editConvertParams')" :title="t('editor.toolbar.editConvertParams')">
      <MoreOutlined />
    </a-button>
  </div>
</template>

<style scoped>
.editor-toolbar {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 2px 8px;
}
.toolbar-select-btn {
  display: inline-flex;
  align-items: center;
  font-size: 12px;
  height: 28px;
  padding: 0 8px;
  color: #555;
}
.toolbar-select-btn:hover {
  color: #1890ff;
  border-color: #1890ff;
}
.arrow {
  font-size: 8px;
  color: #999;
  margin-left: 4px;
}
.toolbar-icon-btn {
  font-size: 16px;
  padding: 0 6px;
  height: 28px;
  line-height: 1;
  color: #555;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.toolbar-icon-btn:hover {
  color: #1890ff;
  background: rgba(24, 144, 255, 0.06);
}
.toolbar-separator {
  width: 1px;
  height: 20px;
  background: #e8e8e8;
  margin: 0 6px;
}
.active-action {
  font-weight: 600;
  color: #1890ff;
}
</style>
