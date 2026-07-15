// Agent Manager — 子进程管理模块
//
// Agent Manager: subprocess lifecycle management for Python agent processes.
// 管理 Python agent 子进程的启动、标准输入/输出通信和终止。
// Manages spawn, stdin/stdout communication, and termination of agent subprocesses.

use std::collections::HashMap;
use std::io::Write;
use std::process::Child;
use std::sync::Mutex;

// ============================================================================
// Types / 类型定义
// ============================================================================

/// Agent 子进程句柄
/// Agent subprocess handle — holds the child process and its stdin pipe.
pub struct AgentHandle {
    pub child: Child,
    pub stdin: std::process::ChildStdin,
}

/// 全局 agent 进程管理器
/// Global agent process manager — maps task_id to child process handle.
pub struct AgentManager {
    pub agents: Mutex<HashMap<String, AgentHandle>>,
}

impl AgentManager {
    pub fn new() -> Self {
        Self {
            agents: Mutex::new(HashMap::new()),
        }
    }

    /// 注册（或替换）一个 agent 进程。
    /// Insert (or replace) an agent process.
    pub fn insert(&self, task_id: String, handle: AgentHandle) -> Result<(), String> {
        let mut agents = self.agents.lock().map_err(|e| e.to_string())?;
        // 如果已有同名任务，先 kill / If task_id already exists, kill old one first
        if let Some(mut old_handle) = agents.remove(&task_id) {
            let _ = old_handle.child.kill();
        }
        agents.insert(task_id, handle);
        Ok(())
    }

    /// 向指定 agent 发送命令。
    /// Send a command to the specified agent.
    pub fn send_command(&self, task_id: &str, command: &str) -> Result<(), String> {
        let mut agents = self.agents.lock().map_err(|e| e.to_string())?;
        let handle = agents
            .get_mut(task_id)
            .ok_or_else(|| format!("Agent task not found: {}", task_id))?;
        writeln!(handle.stdin, "{}", command)
            .map_err(|e| format!("Failed to write command to agent stdin: {}", e))?;
        handle.stdin.flush()
            .map_err(|e| format!("Failed to flush agent stdin: {}", e))?;
        Ok(())
    }

    /// 终止指定的 agent 进程。
    /// Kill the specified agent process.
    pub fn kill(&self, task_id: &str) -> Result<(), String> {
        let mut agents = self.agents.lock().map_err(|e| e.to_string())?;
        if let Some(mut handle) = agents.remove(task_id) {
            // 先尝试通过 stdin 发送 terminate 命令 / Try graceful termination first
            let terminate_cmd = "{\"command\":\"terminate\",\"prompt_id\":\"\"}";
            let _ = writeln!(handle.stdin, "{}", terminate_cmd);
            let _ = handle.stdin.flush();

            // 等待一小段时间 / Wait briefly
            std::thread::sleep(std::time::Duration::from_secs(2));

            // 强制终止 / Force kill
            let _ = handle.child.kill();
            let _ = handle.child.wait();
            Ok(())
        } else {
            Err(format!("Agent task not found: {}", task_id))
        }
    }

    /// 清理已退出进程的句柄。
    /// Clean up handle for an exited process.
    pub fn cleanup(&self, task_id: &str) -> Result<Option<i32>, String> {
        let mut agents = self.agents.lock().map_err(|e| e.to_string())?;
        if let Some(mut handle) = agents.remove(task_id) {
            match handle.child.try_wait() {
                Ok(Some(status)) => {
                    let code = status.code();
                    Ok(code)
                }
                Ok(None) => {
                    // 进程还在运行，放回去 / Process still running, put it back
                    agents.insert(task_id.to_string(), handle);
                    Ok(None) // None 表示仍在运行 / None means still running
                }
                Err(_) => Ok(None),
            }
        } else {
            Ok(Some(-1)) // 未找到 / Not found
        }
    }

    /// 检查是否有 agent 子进程在运行（同时清理已退出的进程）。
    /// Check whether any agent subprocess is running (also cleans up exited ones).
    pub fn has_running(&self) -> Result<bool, String> {
        let mut agents = self.agents.lock().map_err(|e| e.to_string())?;
        let mut running = false;
        // 清理已退出的进程，保留仍在运行的 / Clean up exited, keep running
        agents.retain(|_id, handle| {
            match handle.child.try_wait() {
                Ok(Some(_)) => false,       // 已退出 / Exited
                _ => { running = true; true } // 仍在运行 / Still running
            }
        });
        Ok(running)
    }

    /// 终止所有 agent 子进程。
    /// Kill all agent subprocesses.
    pub fn kill_all(&self) -> Result<(), String> {
        let mut agents = self.agents.lock().map_err(|e| e.to_string())?;
        for (_id, mut handle) in agents.drain() {
            let _ = handle.child.kill();
            let _ = handle.child.wait();
        }
        Ok(())
    }
}
