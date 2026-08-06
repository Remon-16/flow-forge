/** 可拖拽分隔条 composable / Draggable splitter composable.

提供水平和垂直方向的拖拽调整大小功能。
Provides horizontal and vertical drag-to-resize functionality.

用法 / Usage:
  const { size, isDragging, dividerProps } = useSplitter(ref, {
    direction: 'vertical',   // 'horizontal' | 'vertical'
    defaultSize: 300,        // 默认像素大小
    minSize: 100,            // 最小像素大小
    maxSize: 800,            // 最大像素大小（可选）
    reverse: false,          // true 时拖拽方向反转
  })
*/

import { ref, onUnmounted } from 'vue'

export interface SplitterOptions {
  /** 分隔方向: horizontal (上/下) 或 vertical (左/右) */
  direction: 'horizontal' | 'vertical'
  /** 默认大小 (px) */
  defaultSize: number
  /** 最小大小 (px) */
  minSize: number
  /** 最大大小 (px), 不设则无上限 */
  maxSize?: number
  /** 是否反转拖拽方向 (如拖动上方分隔条调整上方区域) */
  reverse?: boolean
}

export interface SplitterReturn {
  /** 当前面板大小 (px) */
  size: ReturnType<typeof ref<number>>
  /** 是否正在拖拽 */
  isDragging: ReturnType<typeof ref<boolean>>
  /** 绑定到分隔条元素的事件处理器 */
  onDividerMousedown: (e: MouseEvent) => void
}

export function useSplitter(options: SplitterOptions): SplitterReturn {
  const size = ref(options.defaultSize)
  const isDragging = ref(false)
  const { direction, minSize, maxSize, reverse } = options

  function onDividerMousedown(e: MouseEvent) {
    e.preventDefault()
    isDragging.value = true
    const startPos = direction === 'horizontal' ? e.clientY : e.clientX
    const startSize = size.value

    function onMouseMove(ev: MouseEvent) {
      const currentPos = direction === 'horizontal' ? ev.clientY : ev.clientX
      const delta = currentPos - startPos
      const newSize = reverse ? startSize - delta : startSize + delta
      size.value = Math.max(minSize, Math.min(maxSize ?? Infinity, newSize))
    }

    function onMouseUp() {
      isDragging.value = false
      document.removeEventListener('mousemove', onMouseMove)
      document.removeEventListener('mouseup', onMouseUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }

    document.addEventListener('mousemove', onMouseMove)
    document.addEventListener('mouseup', onMouseUp)
    document.body.style.cursor = direction === 'horizontal' ? 'row-resize' : 'col-resize'
    document.body.style.userSelect = 'none'
  }

  onUnmounted(() => {
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
  })

  return { size, isDragging, onDividerMousedown }
}
