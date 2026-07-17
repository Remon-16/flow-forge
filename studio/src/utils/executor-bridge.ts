// Executor Bridge — Tauri invoke wrapper for executor subprocess management.
// 执行器桥接 — Tauri invoke 封装，用于执行器子进程管理。

import { invoke } from '@tauri-apps/api/core'
import { listen, type UnlistenFn } from '@tauri-apps/api/event'
import { isDesktop } from './desktop-bridge'

// ============================================================================
// Subprocess operations / 子进程操作
// ============================================================================

/**
 * 启动执行器子进程。
 * Spawn an executor subprocess. Returns immediately; runs in background.
 */
export async function spawnExecutor(
  sessionId: string,
  workingDir: string,
  pythonExe: string,
  preArgs: string[],
  args: string[],
): Promise<void> {
  if (!isDesktop) throw new Error('Executor requires desktop mode')
  await invoke('spawn_executor', { taskId: sessionId, workingDir, pythonExe, preArgs, args })
}

/**
 * 终止执行器子进程。
 * Kill an executor subprocess.
 */
export async function killExecutor(sessionId: string): Promise<void> {
  if (!isDesktop) throw new Error('Executor requires desktop mode')
  await invoke('kill_executor', { taskId: sessionId })
}

/**
 * 检查执行器子进程是否仍在运行。
 * Check whether an executor subprocess is still running.
 */
export async function checkExecutorRunning(sessionId: string): Promise<boolean> {
  if (!isDesktop) return false
  return invoke<boolean>('check_executor_running', { taskId: sessionId })
}

// ============================================================================
// Event listeners / 事件监听
// ============================================================================

/**
 * 监听执行器子进程输出事件。
 * Listen to executor subprocess output events (stdout + stderr).
 * Returns an unlisten function to clean up.
 */
export function listenToExecutorEvents(
  sessionId: string,
  handler: (line: string, level: 'info' | 'error') => void,
): () => void {
  const unlisteners: UnlistenFn[] = []

  // 监听 stdout 事件 / Listen to stdout events
  listen<{ task_id: string; line: string }>('executor-stdout', (event) => {
    if (event.payload.task_id !== sessionId) return
    handler(event.payload.line, 'info')
  }).then((fn) => unlisteners.push(fn))

  // 监听 stderr 事件 / Listen to stderr events
  listen<{ task_id: string; line: string }>('executor-stderr', (event) => {
    if (event.payload.task_id !== sessionId) return
    handler(event.payload.line, 'error')
  }).then((fn) => unlisteners.push(fn))

  // 返回清理函数 / Return cleanup function
  return () => {
    unlisteners.forEach((fn) => fn())
  }
}
