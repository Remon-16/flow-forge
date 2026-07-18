// Converter Bridge — Tauri invoke wrapper for converter subprocess management.
// 转换器桥接 — Tauri invoke 封装，用于转换器子进程管理。

import { invoke } from '@tauri-apps/api/core'
import { listen } from '@tauri-apps/api/event'
import { isDesktop } from './desktop-bridge'
import { parseStderrLine } from './log-parser'

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
  preArgs: string[],
  args: string[],
): Promise<void> {
  if (!isDesktop) throw new Error('Converter requires desktop mode')
  await invoke('spawn_converter', { taskId: sessionId, workingDir, pythonExe, preArgs, args })
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
export async function listenToConverterEvents(
  sessionId: string,
  handler: (line: string, level: 'info' | 'warn' | 'error') => void,
): Promise<() => void> {
  // 先注册监听器再返回，确保 spawn 进程前事件通道已就绪。
  // Await listener registration before returning so the event channel
  // is ready before the process is spawned — prevents race-condition data loss.

  // 监听 stdout 事件 / Listen to stdout events
  const unlistenStdout = await listen<{ task_id: string; line: string }>('converter-stdout', (event) => {
    if (event.payload.task_id !== sessionId) return
    handler(event.payload.line, 'info')
  })

  // 监听 stderr 事件 — JSON 解析提取级别（兜底非 JSON 行按 info 处理）
  // Listen to stderr events — JSON parse for level (non-JSON fallback to info)
  const unlistenStderr = await listen<{ task_id: string; line: string }>('converter-stderr', (event) => {
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
