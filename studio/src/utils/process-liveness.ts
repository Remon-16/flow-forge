// 进程存活检查工具 — 跨 store 共享的子进程状态验证。
// Process liveness check — shared subprocess status verification for stores.

/** 状态修复时设置的统一错误消息 / Unified error message when fixing stale status */
export const STALE_STATUS_ERROR_MSG = 'Process lost: Studio was closed or crashed'
//
// ProcessManager 是纯内存结构（Mutex<HashMap<...>>），Studio 重启后为空。
// 持久化的 running 状态在新 session 中一定是过期的 —— 旧进程已被 Job Object 终止。
// ProcessManager is in-memory only — empty after restart. Any persisted 'running'
// status is definitely stale; old processes were killed by the Job Object.

/**
 * 检查并修复启动时残留的 running/question 状态。
 * Check and fix stale running/question status on startup.
 *
 * 对每个 stuckStatuses 中的 item 调用 checkRunning()：
 * - 返回 false → 标记为 'error'（进程已死）
 * - 返回 true  → 保留原状态（进程意外存活，保留供人工判断）
 * - 抛出异常   → 保守标记为 'error'（IPC 不可用）
 *
 * For each item whose status is in stuckStatuses, calls checkRunning():
 * - Returns false → mark as 'error' (process is dead)
 * - Returns true  → keep original status (process survived unexpectedly; keep for manual review)
 * - Throws        → conservatively mark as 'error' (IPC unavailable)
 *
 * @param items          - 待检查的任务/会话列表 / List of tasks/sessions to check
 * @param checkRunning   - 进程存活检查函数（调用 Tauri IPC）/ Process liveness check function (calls Tauri IPC)
 * @param stuckStatuses  - 需要检查的状态列表，如 ['running'] 或 ['running', 'question'] / Statuses that need checking
 * @param errorMessage   - 标记为 error 时设置的消息 / Error message to set when marking as error
 * @returns true 如果有任何状态被修复（调用方需要持久化）/ true if any status was fixed (caller should persist)
 */
export async function fixStaleRunningStatus<T extends { id: string; status: string; error?: string }>(
  items: T[],
  checkRunning: (id: string) => Promise<boolean>,
  stuckStatuses: string[],
  errorMessage: string,
): Promise<boolean> {
  let changed = false
  for (const item of items) {
    if (!stuckStatuses.includes(item.status)) continue
    let alive = false
    try {
      alive = await checkRunning(item.id)
    } catch {
      // IPC 调用失败（非桌面模式或 Tauri 未就绪），保守标记为 error
      // IPC call failed (non-desktop mode or Tauri not ready), conservatively mark as error
    }
    if (!alive) {
      item.status = 'error' as T['status']
      item.error = errorMessage
      changed = true
    }
  }
  return changed
}
