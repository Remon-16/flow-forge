// Converter Bridge — Tauri invoke wrapper for converter subprocess management.
// 转换器桥接 — Tauri invoke 封装，用于转换器子进程管理。

import { invoke } from '@tauri-apps/api/core'
import { listen, type UnlistenFn } from '@tauri-apps/api/event'
import { isDesktop } from './desktop-bridge'

// ============================================================================
// Subprocess operations / 子进程操作
// ============================================================================

/**
 * 启动转换器子进程。
 * Spawn a converter subprocess. Returns immediately; runs in background.
 */
export async function spawnConverter(
  sessionId: string,
  workingDir: string,
  pythonExe: string,
  args: string[],
): Promise<void> {
  if (!isDesktop) throw new Error('Converter requires desktop mode')
  await invoke('spawn_converter', { taskId: sessionId, workingDir, pythonExe, args })
}

/**
 * 终止转换器子进程。
 * Kill a converter subprocess.
 */
export async function killConverter(sessionId: string): Promise<void> {
  if (!isDesktop) throw new Error('Converter requires desktop mode')
  await invoke('kill_converter', { taskId: sessionId })
}

/**
 * 检查转换器子进程是否仍在运行。
 * Check whether a converter subprocess is still running.
 */
export async function checkConverterRunning(sessionId: string): Promise<boolean> {
  if (!isDesktop) return false
  return invoke<boolean>('check_converter_running', { taskId: sessionId })
}

// ============================================================================
// Event listeners / 事件监听
// ============================================================================

/**
 * 监听转换器子进程输出事件。
 * Listen to converter subprocess output events (stdout + stderr).
 * Returns an unlisten function to clean up.
 */
export function listenToConverterEvents(
  sessionId: string,
  handler: (line: string, level: 'info' | 'error') => void,
): () => void {
  const unlisteners: UnlistenFn[] = []

  // 监听 stdout 事件 / Listen to stdout events
  listen<{ task_id: string; line: string }>('converter-stdout', (event) => {
    if (event.payload.task_id !== sessionId) return
    handler(event.payload.line, 'info')
  }).then((fn) => unlisteners.push(fn))

  // 监听 stderr 事件 / Listen to stderr events
  listen<{ task_id: string; line: string }>('converter-stderr', (event) => {
    if (event.payload.task_id !== sessionId) return
    handler(event.payload.line, 'error')
  }).then((fn) => unlisteners.push(fn))

  // 返回清理函数 / Return cleanup function
  return () => {
    unlisteners.forEach((fn) => fn())
  }
}
