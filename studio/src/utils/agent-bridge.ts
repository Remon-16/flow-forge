// Agent Bridge — Tauri invoke wrapper for agent subprocess management.
// 智能体桥接 — Tauri invoke 封装，用于 agent 子进程管理。

import { invoke } from '@tauri-apps/api/core'
import { listen } from '@tauri-apps/api/event'
import { isDesktop } from './desktop-bridge'
import type { AgentEvent } from '../types/agent'

// ============================================================================
// Subprocess operations / 子进程操作
// ============================================================================

/**
 * 启动 agent 子进程。
 * Spawn an agent subprocess. Returns immediately; the agent runs in background.
 */
export async function spawnAgent(
  taskId: string,
  workingDir: string,
  pythonExe: string,
  preArgs: string[],
  args: string[],
): Promise<void> {
  if (!isDesktop) throw new Error('Agent execution requires desktop mode')
  await invoke('spawn_agent', { taskId, workingDir, pythonExe, preArgs, args })
}

/**
 * 向 agent 子进程发送 JSON 命令。
 * Send a JSON command to an agent subprocess via stdin.
 */
export async function sendToAgent(
  taskId: string,
  command: string,
): Promise<void> {
  if (!isDesktop) throw new Error('Agent execution requires desktop mode')
  await invoke('send_to_agent', { taskId, command })
}

/**
 * 终止 agent 子进程。
 * Kill an agent subprocess.
 */
export async function killAgent(taskId: string): Promise<void> {
  if (!isDesktop) throw new Error('Agent execution requires desktop mode')
  await invoke('kill_agent', { taskId })
}

/**
 * 检查 agent 子进程是否仍在运行。
 * Check whether an agent subprocess is still running.
 */
export async function checkAgentRunning(taskId: string): Promise<boolean> {
  if (!isDesktop) return false
  return invoke<boolean>('check_agent_running', { taskId })
}

// ============================================================================
// Event listeners / 事件监听
// ============================================================================

/**
 * 监听 agent 子进程输出事件。
 * Listen to agent subprocess output events (stdout + stderr).
 * Returns an unlisten function to clean up.
 */
export async function listenToAgentEvents(
  taskId: string,
  handler: (event: AgentEvent) => void,
): Promise<() => void> {
  // 先注册监听器再返回，确保 spawn 进程前事件通道已就绪。
  // Await listener registration before returning so the event channel
  // is ready before the process is spawned — prevents race-condition data loss.

  // 监听 stdout JSON 事件 / Listen to stdout JSON events
  const unlistenStdout = await listen<{ task_id: string; line: string }>('agent-stdout', (event) => {
    if (event.payload.task_id !== taskId) return
    try {
      const parsed = JSON.parse(event.payload.line) as AgentEvent
      handler(parsed)
    } catch {
      // 非 JSON 行 → 视为普通日志 / Non-JSON line → treat as log
      handler({
        type: 'log',
        level: 'info',
        message: event.payload.line,
        ts: new Date().toLocaleTimeString(),
      })
    }
  })

  // 监听 stderr 事件 / Listen to stderr events
  const unlistenStderr = await listen<{ task_id: string; line: string }>('agent-stderr', (event) => {
    if (event.payload.task_id !== taskId) return
    handler({
      type: 'log',
      level: 'error',
      message: event.payload.line,
      ts: new Date().toLocaleTimeString(),
    })
  })

  // 返回清理函数 / Return cleanup function
  return () => {
    unlistenStdout()
    unlistenStderr()
  }
}
