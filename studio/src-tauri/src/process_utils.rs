// 进程工具模块 — 跨平台子进程操作的分发层。
// Process utility module — cross-platform dispatch layer for subprocess operations.
//
// 平台特定实现位于独立文件：
// Platform-specific implementations live in separate files:
//   process_utils_windows.rs — Windows: taskkill, DETACHED_PROCESS
//   process_utils_unix.rs    — Unix:    kill -9, process_group(0)
//
// 本模块提供统一的公共 API，编译期通过 #[cfg] + #[path] 选择平台实现。
// 共享兜底逻辑（child.kill() 等）和纯跨平台逻辑（terminate_python_process）也在本模块。
// This module provides a unified public API. Platform implementations are selected
// at compile time via #[cfg] + #[path]. Shared fallback logic and pure cross-platform
// functions (terminate_python_process) also live here.

use std::io::Write;
use std::process::{Child, ChildStdin, Command};

// ============================================================================
// 编译期平台选择 / Compile-time platform selection
// ============================================================================

#[cfg(target_os = "windows")]
#[path = "process_utils_windows.rs"]
mod platform_impl;

#[cfg(unix)]
#[path = "process_utils_unix.rs"]
mod platform_impl;

// ============================================================================
// 跨平台 spawn 配置 / Cross-platform spawn configuration
// ============================================================================

/// 禁止子进程弹出控制台/终端窗口（跨平台分发）。
/// Suppress console/terminal window (cross-platform dispatch).
///
/// Windows → DETACHED_PROCESS；Unix → no-op。
pub fn suppress_console_window(cmd: &mut Command) {
    platform_impl::suppress_console_window(cmd);
}

/// 设置进程组（跨平台分发）。
/// Set process group (cross-platform dispatch).
///
/// Unix → process_group(0)；Windows → no-op（taskkill /T 通过 ParentProcessId 枚举子进程）。
pub fn apply_process_group(cmd: &mut Command) {
    platform_impl::apply_process_group(cmd);
}

// ============================================================================
// Kill 函数 / Kill functions
// ============================================================================

/// 强制终止子进程及其所有后代进程（跨平台）。
/// Force-kill a child process and all its descendants (cross-platform).
///
/// 1. 平台特定进程树终止（taskkill /T 或 kill -9 -PGID）
/// 2. child.kill() 兜底
/// 3. child.try_wait() 回收僵尸
///
/// 1. Platform-specific tree kill (taskkill /T or kill -9 -PGID)
/// 2. child.kill() fallback
/// 3. child.try_wait() zombie reaping
pub fn kill_process_tree(child: &mut Child) {
    let pid = child.id();

    // 平台特定：进程树终止 / Platform-specific: tree kill
    platform_impl::kill_process_tree(child);

    // 兜底：终止直接子进程并回收僵尸 / Fallback: kill direct child and reap zombie
    if let Err(e) = child.kill() {
        log::warn!("[kill_process_tree] child.kill() failed for PID {}: {}", pid, e);
    }
    let _ = child.try_wait();
}

/// 终止 Python 子进程：先发送优雅终止通知，再强制 kill 进程树。
/// Terminate a Python subprocess: graceful stdin notify, then force-kill tree.
///
/// 这是 agent / executor / converter 进程终止的**唯一入口**。
/// 业务代码不应自行实现 kill 逻辑，统一调用此函数。
/// This is the SINGLE entry point for terminating agent/executor/converter processes.
/// Business code MUST NOT implement kill logic directly — always call this function.
pub fn terminate_python_process(child: &mut Child, stdin: &mut ChildStdin) {
    // 优雅终止：通过 stdin 发送 terminate 命令让 Python 端有机会做清理
    // Graceful termination: send terminate command via stdin so Python can clean up
    let terminate_cmd = "{\"command\":\"terminate\",\"prompt_id\":\"\"}";
    let _ = writeln!(stdin, "{}", terminate_cmd);
    let _ = stdin.flush();

    // 强制终止进程树 / Force-kill the process tree
    kill_process_tree(child);
}
