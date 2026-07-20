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
  height: 6px;                  /* 高度从 4→6px / height 4→6px */
  cursor: row-resize;
}
/* 透明扩展可点击区域 / Transparently expand clickable area */
.divider-horizontal::before {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  top: -4px;                   /* 向上扩展 4px */
  bottom: -4px;                 /* 向下扩展 4px */
}
.divider-horizontal .divider-handle {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  width: 48px;                  /* 略微加长 / slightly longer */
  height: 6px;
}

.divider-vertical {
  width: 6px;                   /* 宽度从 4→6px / width 4→6px */
  cursor: col-resize;
}
/* 透明扩展可点击区域 / Transparently expand clickable area */
.divider-vertical::before {
  content: '';
  position: absolute;
  left: -4px;                   /* 向左扩展 4px */
  right: -4px;                  /* 向右扩展 4px */
  top: 0;
  bottom: 0;
}
.divider-vertical .divider-handle {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  width: 6px;
  height: 48px;                 /* 略微加长 / slightly taller */
}
</style>
