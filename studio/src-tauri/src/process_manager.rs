// 进程注册表 — 通用 Python 子进程生命周期管理模块。
// Process Registry: generic Python subprocess lifecycle management.
//
// 管理 agent / executor / converter 全部子进程的注册、通信和清理。
// 本模块不包含任何 kill 实现代码 — 所有终止逻辑委托给 process_utils 工具模块。
// Manages registration, communication, and cleanup for all subprocess types.
// Contains ZERO kill implementation — all termination delegated to process_utils.

use std::collections::HashMap;
use std::io::Write;
use std::process::Child;
use std::sync::Mutex;

use crate::job_manager::JobHandle;
use crate::process_utils::terminate_python_process;

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
/// agent / executor / converter 共享同一个注册表实例。
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
    pub fn insert(&self, task_id: String, handle: ProcessHandle) -> Result<(), String> {
        let mut processes = self.processes.lock().map_err(|e| e.to_string())?;
        // 如果已有同名任务，先通过统一终止入口 kill 旧进程（含优雅 stdin 通知）
        // If task_id already exists, kill old one via unified terminate entry (incl. graceful stdin notify)
        if let Some(mut old_handle) = processes.remove(&task_id) {
            terminate_python_process(&mut old_handle.child, &mut old_handle.stdin);
        }
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
        handle.stdin.flush()
            .map_err(|e| format!("Failed to flush stdin: {}", e))?;
        Ok(())
    }

    /// 终止指定子进程（委托给 process_utils）。
    /// Kill the specified subprocess (delegates to process_utils).
    pub fn kill(&self, task_id: &str) -> Result<(), String> {
        let mut processes = self.processes.lock().map_err(|e| e.to_string())?;
        if let Some(mut handle) = processes.remove(task_id) {
            // 取出 handle 后立即释放 mutex 锁，避免阻塞其他操作
            // Release mutex lock immediately after removing handle
            drop(processes);

            // 委托工具模块执行终止（优雅通知 + 强制 kill 进程树）
            // Delegate to utility module (graceful notify + force-kill tree)
            terminate_python_process(&mut handle.child, &mut handle.stdin);
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

    /// 终止所有子进程（委托给 process_utils）。
    /// Kill all subprocesses (delegates to process_utils).
    pub fn kill_all(&self) -> Result<(), String> {
        let mut processes = self.processes.lock().map_err(|e| e.to_string())?;
        for (_id, mut handle) in processes.drain() {
            terminate_python_process(&mut handle.child, &mut handle.stdin);
        }
        Ok(())
    }
}
