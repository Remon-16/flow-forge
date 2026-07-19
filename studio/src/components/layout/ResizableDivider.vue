<!-- 可拖拽分隔条 / Resizable divider.
     支持水平和垂直两种方向。
     Supports horizontal (top/bottom) and vertical (left/right) orientations. -->

<script setup lang="ts">
defineProps<{
  /** 分隔方向: horizontal (上下) 或 vertical (左右) */
  orientation: 'horizontal' | 'vertical'
}>()

const emit = defineEmits<{
  mousedown: [e: MouseEvent]
}>()

function onMousedown(e: MouseEvent) {
  emit('mousedown', e)
}
</script>

<template>
  <div
    class="resizable-divider"
    :class="'divider-' + orientation"
    @mousedown="onMousedown"
  >
    <div class="divider-handle" />
  </div>
</template>

<style scoped>
.resizable-divider {
  flex-shrink: 0;
  position: relative;
  background: transparent;
  z-index: 10;
}
.resizable-divider:hover,
.resizable-divider:active {
  background: #fa8c16;
}

.divider-horizontal {
  height: 4px;
  cursor: row-resize;
}
.divider-horizontal .divider-handle {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  width: 40px;
  height: 4px;
}

.divider-vertical {
  width: 4px;
  cursor: col-resize;
}
.divider-vertical .divider-handle {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  width: 4px;
  height: 40px;
}
</style>
