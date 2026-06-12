<script setup lang="ts">
import type { OpenTab } from '../../stores/yaml-store'

defineProps<{
  tabs: OpenTab[]
  activeIndex: number
}>()

const emit = defineEmits<{
  (e: 'switch', index: number): void
  (e: 'close', index: number): void
}>()
</script>

<template>
  <div class="yaml-tab-bar" v-if="tabs.length > 0">
    <div
      v-for="(tab, i) in tabs"
      :key="i"
      class="yaml-tab"
      :class="{ active: i === activeIndex }"
      @click="emit('switch', i)"
    >
      <span class="tab-dot" v-if="tab.modified" title="Modified">&#9679;</span>
      <span class="tab-title">{{ tab.title }}</span>
      <span class="tab-close" @click.stop="emit('close', i)" title="Close">&times;</span>
    </div>
  </div>
</template>

<style scoped>
.yaml-tab-bar {
  display: flex;
  background: #f0f0f0;
  border-bottom: 1px solid #d9d9d9;
  overflow-x: auto;
  flex-shrink: 0;
}

.yaml-tab {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  cursor: pointer;
  border-right: 1px solid #d9d9d9;
  font-size: 12px;
  white-space: nowrap;
  user-select: none;
  min-width: 0;
}

.yaml-tab:hover {
  background: #e8e8e8;
}

.yaml-tab.active {
  background: #fff;
  border-bottom: 2px solid #1890ff;
}

.tab-dot {
  color: #1890ff;
  font-size: 10px;
  line-height: 1;
}

.tab-title {
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 160px;
}

.tab-close {
  font-size: 14px;
  font-weight: bold;
  color: #999;
  width: 16px;
  height: 16px;
  line-height: 16px;
  text-align: center;
  border-radius: 2px;
}

.tab-close:hover {
  background: #d9d9d9;
  color: #333;
}
</style>
