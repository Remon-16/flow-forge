<script setup lang="ts">
// CaseSelectModal — 用例选择模态框。
// Modal for selecting specific test cases to run or convert.
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const props = defineProps<{
  visible: boolean
  /** 用例列表（名称 + 类型 + 标识符）/ Case list with name, type, and identifier */
  cases: { id: string; name: string; type: 'single' | 'biz'; sheetName?: string }[]
}>()

const emit = defineEmits<{
  'update:visible': [v: boolean]
  'confirm': [selectedIds: string[]]
}>()

const selectedIds = ref<string[]>([])

watch(() => props.visible, (v) => {
  if (v) {
    selectedIds.value = []
  }
})

function handleConfirm() {
  emit('confirm', [...selectedIds.value])
  emit('update:visible', false)
}

function handleCancel() {
  emit('update:visible', false)
}

function toggleSelectAll() {
  if (selectedIds.value.length === props.cases.length) {
    selectedIds.value = []
  } else {
    selectedIds.value = props.cases.map(c => c.id)
  }
}

const singleCases = () => props.cases.filter(c => c.type === 'single')
const bizCases = () => props.cases.filter(c => c.type === 'biz')
</script>

<template>
  <a-modal
    :open="visible"
    :title="t('editor.caseSelect.title')"
    width="560px"
    @ok="handleConfirm"
    @cancel="handleCancel"
    :ok-text="t('editor.caseSelect.confirm')"
    :cancel-text="t('dialog.cancel')"
  >
    <div class="select-all">
      <a-checkbox
        :checked="selectedIds.length === cases.length"
        :indeterminate="selectedIds.length > 0 && selectedIds.length < cases.length"
        @change="toggleSelectAll"
      >
        {{ t('editor.caseSelect.selectAll') }} ({{ selectedIds.length }}/{{ cases.length }})
      </a-checkbox>
    </div>

    <!-- 单接口用例 / Single API cases -->
    <div v-if="singleCases().length > 0" class="case-group">
      <div class="group-label">{{ t('editor.caseSelect.singleCases') }} ({{ singleCases().length }})</div>
      <div
        v-for="c in singleCases()"
        :key="c.id"
        class="case-item"
      >
        <a-checkbox
          :checked="selectedIds.includes(c.id)"
          @change="(e: any) => {
            if (e.target.checked) selectedIds.push(c.id)
            else selectedIds = selectedIds.filter(i => i !== c.id)
          }"
        >
          {{ c.name }}
        </a-checkbox>
        <a-tag v-if="c.sheetName" size="small" style="margin-left: 8px">{{ c.sheetName }}</a-tag>
      </div>
    </div>

    <!-- 业务链路 / Biz flows -->
    <div v-if="bizCases().length > 0" class="case-group">
      <div class="group-label">{{ t('editor.caseSelect.bizFlows') }} ({{ bizCases().length }})</div>
      <div
        v-for="c in bizCases()"
        :key="c.id"
        class="case-item"
      >
        <a-checkbox
          :checked="selectedIds.includes(c.id)"
          @change="(e: any) => {
            if (e.target.checked) selectedIds.push(c.id)
            else selectedIds = selectedIds.filter(i => i !== c.id)
          }"
        >
          {{ c.name }}
        </a-checkbox>
        <a-tag v-if="c.sheetName" size="small" style="margin-left: 8px">{{ c.sheetName }}</a-tag>
      </div>
    </div>
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
