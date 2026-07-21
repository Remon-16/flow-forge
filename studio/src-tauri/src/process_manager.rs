// 进程注册表 — 通用 Python 子进程生命周期管理模块。
// Process Registry: generic Python subprocess lifecycle management.
//
// 管理 agent / executor / converter / counter 全部子进程的注册、通信和清理。
// 本模块不包含任何 kill 实现代码 — 所有终止逻辑委托给 process_utils 工具模块。
// Manages registration, communication, and cleanup for all subprocess types.
// Contains ZERO kill implementation — all termination delegated to process_utils.
//
// Kill 策略（每平台唯一）/ Kill strategy (one per platform):
//   Windows → ProcessHandle drop → JobHandle::drop() → CloseHandle → OS KILL_ON_JOB_CLOSE
//   Linux   → kill -9 -PGID（主动kill） + 守护进程（父进程崩溃保护）
//   macOS   → kill -9 -PGID（主动kill） + 守护进程（父进程崩溃保护）

use std::collections::HashMap;
use std::io::Write;
use std::process::Child;
use std::sync::Mutex;

use crate::job_manager::JobHandle;

// ============================================================================
// Types / 类型定义
// ============================================================================

/// 子进程句柄 — 持有子进程对象、stdin 管道及 Job Object 句柄。
/// Process handle — holds the child process, stdin pipe, and Job Object handle.
pub struct ProcessHandle {
    pub child: Child,
    pub stdin: std::process::ChildStdin,
    /// Windows Job Object 句柄（非 Windows 为 None）。
    /// drop 时关闭句柄，OS 通过 KILL_ON_JOB_CLOSE 终止 Job 内所有进程。
    /// Windows Job Object handle (None on non-Windows).
    /// Dropping this closes the handle; OS kills all processes in the Job via KILL_ON_JOB_CLOSE.
    #[allow(dead_code)]
    pub job_handle: Option<JobHandle>,
}

/// 全局进程注册表 — 将 task_id 映射到子进程句柄。
/// Global process registry — maps task_id to child process handle.
/// agent / executor / converter / counter 共享同一个注册表实例。
pub struct ProcessManager {
    pub processes: Mutex<HashMap<String, ProcessHandle>>,
}

impl ProcessManager {
    pub fn new() -> Self {
        Self {
            processes: Mutex::new(HashMap::new()),
        }
    }

    /// 注册（或替换）一个子进程。
    /// Insert (or replace) a subprocess.
    ///
    /// 如有同 task_id 的旧进程，旧 ProcessHandle 被立即 drop：
    ///   Windows → JobHandle drop → OS KILL_ON_JOB_CLOSE
    ///   Non-Windows → 调用方应在调用 insert 前自行 kill 旧进程
    /// If an old process with the same task_id exists, it is immediately dropped.
    pub fn insert(&self, task_id: String, handle: ProcessHandle) -> Result<(), String> {
        let mut processes = self.processes.lock().map_err(|e| e.to_string())?;
        // HashMap::insert 返回旧值（如有），旧 ProcessHandle 立即 drop。
        // HashMap::insert returns old value (if any); old ProcessHandle dropped.
        // Windows 上旧进程被 JobHandle drop → KILL_ON_JOB_CLOSE 自动终止。
        processes.insert(task_id, handle);
        Ok(())
    }

    /// 向指定子进程发送 stdin 命令。
    /// Send a command to the specified subprocess via stdin.
    pub fn send_command(&self, task_id: &str, command: &str) -> Result<(), String> {
        let mut processes = self.processes.lock().map_err(|e| e.to_string())?;
        let handle = processes
            .get_mut(task_id)
            .ok_or_else(|| format!("Task not found: {}", task_id))?;
        writeln!(handle.stdin, "{}", command)
            .map_err(|e| format!("Failed to write command to stdin: {}", e))?;
        handle.stdin
            .flush()
            .map_err(|e| format!("Failed to flush stdin: {}", e))?;
        Ok(())
    }

    /// 终止指定子进程。
    /// Kill the specified subprocess.
    ///
    /// Windows: ProcessHandle 被移除并立即 drop → JobHandle::drop() → CloseHandle →
    ///          OS KILL_ON_JOB_CLOSE 内核强制终止 Job 内所有进程。
    /// Non-Windows: 先通过 kill_process_tree 杀进程组（kill -9 -PGID），
    ///              再 drop ProcessHandle（Child::drop() 关闭句柄）。
    pub fn kill(&self, task_id: &str) -> Result<(), String> {
        let mut processes = self.processes.lock().map_err(|e| e.to_string())?;
        if let Some(mut handle) = processes.remove(task_id) {
            // 取出 handle 后立即释放 mutex 锁，避免阻塞其他操作
            // Release mutex lock immediately after removing handle
            drop(processes);

            // 非 Windows：显式 kill 进程组（Unix Child::drop() 会阻塞等待进程自然退出）
            // Non-Windows: explicitly kill process group before drop
            // (Unix Child::drop() blocks waiting for natural exit if not killed first)
            if cfg!(not(target_os = "windows")) {
                crate::process_utils::kill_process_tree(&mut handle.child);
            }
            // handle 出作用域 drop：
            //   Windows → JobHandle::drop() → CloseHandle → OS KILL_ON_JOB_CLOSE
            //   Non-Windows → Child::drop() 关闭句柄（进程已被 kill_process_tree 终止）
            Ok(())
        } else {
            Err(format!("Task not found: {}", task_id))
        }
    }

    /// 清理已退出进程的句柄（使用 get_mut 避免竞态）。
    /// Clean up handle for an exited process (uses get_mut to avoid race).
    pub fn cleanup(&self, task_id: &str) -> Result<Option<i32>, String> {
        let mut processes = self.processes.lock().map_err(|e| e.to_string())?;
        if let Some(handle) = processes.get_mut(task_id) {
            match handle.child.try_wait() {
                Ok(Some(status)) => {
                    let code = status.code();
                    // 诊断：记录进程退出码 / Diagnostic: log process exit code
                    log::info!("[cleanup] task={} exited code={:?}", task_id, code);
                    // 确认已退出，移除句柄 / Confirmed dead, remove handle
                    processes.remove(task_id);
                    Ok(code)
                }
                Ok(None) => {
                    // 仍在运行，保留追踪 / Still running, keep tracking
                    Ok(None)
                }
                Err(_) => {
                    // try_wait 出错，保守保留追踪以防进程成为孤儿
                    // try_wait error — conservatively keep tracking to prevent orphan
                    Ok(None)
                }
            }
        } else {
            Ok(Some(-1)) // 未找到 / Not found
        }
    }

    /// 检查是否有子进程在运行（同时清理已退出的进程）。
    /// Check whether any subprocess is running (also cleans up exited ones).
    pub fn has_running(&self) -> Result<bool, String> {
        let mut processes = self.processes.lock().map_err(|e| e.to_string())?;
        let mut running = false;
        // 清理已退出的进程，保留仍在运行的 / Clean up exited, keep running
        processes.retain(|_id, handle| {
            match handle.child.try_wait() {
                Ok(Some(_)) => false,        // 已退出 / Exited
                _ => { running = true; true } // 仍在运行 / Still running
            }
        });
        Ok(running)
    }

    /// 终止所有子进程。
    /// Kill all subprocesses.
    ///
    /// Windows: 清空 HashMap，所有 ProcessHandle drop → 所有 JobHandle drop → OS 终止所有进程。
    /// Non-Windows: 先对每个进程执行 kill_process_tree，再清空。
    pub fn kill_all(&self) -> Result<(), String> {
        let mut processes = self.processes.lock().map_err(|e| e.to_string())?;
        // 非 Windows：先显式 kill 每个进程再 drop
        // Non-Windows: must explicitly kill each before drop
        if cfg!(not(target_os = "windows")) {
            for (_id, mut handle) in processes.drain() {
                crate::process_utils::kill_process_tree(&mut handle.child);
            }
        } else {
            // Windows：直接清空，所有 JobHandle drop → OS KILL_ON_JOB_CLOSE
            processes.clear();
        }
        Ok(())
    }
}
