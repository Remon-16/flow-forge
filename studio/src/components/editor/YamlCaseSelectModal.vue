<script setup lang="ts">
// YamlCaseSelectModal — YAML 文件选择模态框，按 case_type 分组展示。
// Modal for selecting YAML files to run, grouped by case_type.
import { ref, watch, computed } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

export interface YamlCaseFile {
  /** 文件绝对路径 / Absolute file path */
  path: string
  /** 文件名（含相对路径前缀）/ File name (with relative path prefix) */
  name: string
  /** YAML 文件中的 case_type / case_type from the YAML file */
  caseType: 'single' | 'biz' | 'interfaces'
}

const props = defineProps<{
  visible: boolean
  /** YAML 文件列表 / List of YAML files to select from */
  files: YamlCaseFile[]
}>()

const emit = defineEmits<{
  'update:visible': [v: boolean]
  'confirm': [selectedPaths: string[]]
}>()

const selectedPaths = ref<string[]>([])

// 每次打开时重置选择 / Reset selection each time modal opens
watch(() => props.visible, (v) => {
  if (v) {
    selectedPaths.value = []
  }
})

// 按 case_type 分组 / Group by case_type
const singleFiles = computed(() => props.files.filter(f => f.caseType === 'single'))
const bizFiles = computed(() => props.files.filter(f => f.caseType === 'biz'))
const interfaceFiles = computed(() => props.files.filter(f => f.caseType === 'interfaces'))

function handleConfirm() {
  emit('confirm', [...selectedPaths.value])
  emit('update:visible', false)
}

function handleCancel() {
  emit('update:visible', false)
}

function toggleSelectAll() {
  if (selectedPaths.value.length === props.files.length) {
    selectedPaths.value = []
  } else {
    selectedPaths.value = props.files.map(f => f.path)
  }
}
</script>

<template>
  <a-modal
    :open="visible"
    :title="t('editor.yamlCaseSelect.title')"
    width="560px"
    @ok="handleConfirm"
    @cancel="handleCancel"
    :ok-text="t('dialog.confirm')"
    :cancel-text="t('dialog.cancel')"
  >
    <!-- 无文件时的空状态 / Empty state when no files found -->
    <div v-if="files.length === 0" style="text-align: center; padding: 32px; color: #999;">
      {{ t('editor.yamlCaseSelect.noFiles') }}
    </div>

    <template v-else>
      <!-- 全选 / Select All -->
      <div class="select-all">
        <a-checkbox
          :checked="selectedPaths.length === files.length"
          :indeterminate="selectedPaths.length > 0 && selectedPaths.length < files.length"
          @change="toggleSelectAll"
        >
          {{ t('editor.caseSelect.selectAll') }} ({{ selectedPaths.length }}/{{ files.length }})
        </a-checkbox>
      </div>

      <!-- 按 case_type 分组展示 / Grouped by case_type -->
      <div v-for="group in [
        { key: 'single', label: t('editor.caseSelect.singleCases'), items: singleFiles },
        { key: 'biz', label: t('editor.caseSelect.bizFlows'), items: bizFiles },
        { key: 'interfaces', label: t('editor.yamlCaseSelect.interfaces'), items: interfaceFiles },
      ]" :key="group.key">
        <div v-if="group.items.length > 0" class="case-group">
          <div class="group-label">{{ group.label }} ({{ group.items.length }})</div>
          <div
            v-for="f in group.items"
            :key="f.path"
            class="case-item"
          >
            <a-checkbox
              :checked="selectedPaths.includes(f.path)"
              @change="(e: any) => {
                if (e.target.checked) selectedPaths.push(f.path)
                else selectedPaths = selectedPaths.filter(p => p !== f.path)
              }"
            >
              {{ f.name }}
            </a-checkbox>
          </div>
        </div>
      </div>
    </template>
  </a-modal>
</template>

<style scoped>
.select-all {
  padding-bottom: 12px;
  border-bottom: 1px solid #f0f0f0;
  margin-bottom: 12px;
}
.case-group {
  margin-bottom: 16px;
}
.group-label {
  font-size: 13px;
  font-weight: 600;
  color: #666;
  margin-bottom: 8px;
}
.case-item {
  padding: 4px 0;
}
</style>
