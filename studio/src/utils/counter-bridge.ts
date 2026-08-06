// Counter Bridge — Tauri invoke wrapper for counter subprocess management.
// 计数器桥接 — Tauri invoke 封装，用于诊断计数器子进程管理。
// 完全遵循 executor-bridge.ts 模式 / Follows executor-bridge.ts pattern exactly.

import { invoke } from '@tauri-apps/api/core'
import { listen } from '@tauri-apps/api/event'
import { isDesktop } from './desktop-bridge'
import { parseStderrLine } from './log-parser'
import { ENABLE_NON_WINDOWS_SPAWN } from './feature-flags'

// ============================================================================
// Subprocess operations / 子进程操作
// ============================================================================

/**
 * 启动计数器子进程。
 * Spawn a counter subprocess. Returns immediately; runs in background.
 */
export async function spawnCounter(
  sessionId: string,
  workingDir: string,
  pythonExe: string,
  preArgs: string[],
  args: string[],
): Promise<void> {
  if (!isDesktop) throw new Error('Counter requires desktop mode')
  await invoke('spawn_counter', {
    taskId: sessionId, workingDir, pythonExe, preArgs, args,
    allowNonWindows: ENABLE_NON_WINDOWS_SPAWN,
  })
}

/**
 * 终止计数器子进程（委托给 ProcessManager.kill → process_utils.terminate_python_process）。
 * Kill a counter subprocess (delegates to ProcessManager.kill → process_utils.terminate_python_process).
 */
export async function killCounter(sessionId: string): Promise<void> {
  if (!isDesktop) throw new Error('Counter requires desktop mode')
  await invoke('kill_counter', { taskId: sessionId })
}

/**
 * 检查计数器子进程是否仍在运行。
 * Check whether a counter subprocess is still running.
 */
export async function checkCounterRunning(sessionId: string): Promise<boolean> {
  if (!isDesktop) return false
  return invoke<boolean>('check_counter_running', { taskId: sessionId })
}

// ============================================================================
// Event listeners / 事件监听
// ============================================================================

/**
 * 监听计数器子进程输出事件（stdout + stderr）。
 * Listen to counter subprocess output events (stdout + stderr).
 * Returns an unlisten function to clean up.
 */
export async function listenToCounterEvents(
  sessionId: string,
  handler: (line: string, level: 'info' | 'warn' | 'error') => void,
): Promise<() => void> {
  // 先注册监听器再返回，确保 spawn 进程前事件通道已就绪。
  // Await listener registration before returning so the event channel
  // is ready before the process is spawned — prevents race-condition data loss.

  // 监听 stdout 事件 / Listen to stdout events
  const unlistenStdout = await listen<{ task_id: string; line: string }>('counter-stdout', (event) => {
    if (event.payload.task_id !== sessionId) return
    handler(event.payload.line, 'info')
  })

  // 监听 stderr 事件 — JSON 解析提取级别（兜底非 JSON 行按 info 处理）
  // Listen to stderr events — JSON parse for level (non-JSON fallback to info)
  const unlistenStderr = await listen<{ task_id: string; line: string }>('counter-stderr', (event) => {
    if (event.payload.task_id !== sessionId) return
    const parsed = parseStderrLine(event.payload.line)
    handler(parsed.message, parsed.level)
  })

  // 返回清理函数 / Return cleanup function
  return () => {
    unlistenStdout()
    unlistenStderr()
  }
}
