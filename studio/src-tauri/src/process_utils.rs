// 进程工具模块 — 跨平台子进程操作的分发层。
// Process utility module — cross-platform dispatch layer for subprocess operations.
//
// 平台特定实现位于独立文件：
// Platform-specific implementations live in separate files:
//   process_utils_windows.rs — Windows: Job Object, CREATE_NO_WINDOW
//   process_utils_linux.rs   — Linux: process group + prctl guardian
//   process_utils_macos.rs   — macOS: process group + kqueue guardian
//
// 本模块提供统一的公共 API，编译期通过 #[cfg] + #[path] 选择平台实现。
// 共享兜底逻辑（child.kill() 等）和纯跨平台逻辑也在本模块。
// This module provides a unified public API. Platform implementations are selected
// at compile time via #[cfg] + #[path]. Shared fallback logic also lives here.

use std::process::{Child, Command};

// ============================================================================
// 编译期平台选择 / Compile-time platform selection
// ============================================================================

#[cfg(target_os = "windows")]
#[path = "process_utils_windows.rs"]
mod platform_impl;

#[cfg(target_os = "linux")]
#[path = "process_utils_linux.rs"]
mod platform_impl;

#[cfg(target_os = "macos")]
#[path = "process_utils_macos.rs"]
mod platform_impl;

// 未支持平台的兜底实现 — 仅提供空操作，实际 spawn 由 _spawn_python_process 中的 allow_non_windows 守卫阻止。
// Fallback for unsupported platforms — provides no-ops; actual spawn is blocked by the guard in _spawn_python_process.
#[cfg(not(any(target_os = "windows", target_os = "linux", target_os = "macos")))]
mod platform_impl {
    use std::process::{Child, Command};

    pub fn suppress_console_window(_cmd: &mut Command) {
        // no-op
    }

    pub fn apply_process_group(_cmd: &mut Command) {
        // no-op
    }

    pub fn kill_process_tree(child: &mut Child) {
        // 兜底：直接 kill 直接子进程 / Fallback: kill direct child
        let _ = child.kill();
        let _ = child.try_wait();
    }
}

// ============================================================================
// 跨平台 spawn 配置 / Cross-platform spawn configuration
// ============================================================================

/// 禁止子进程弹出控制台/终端窗口（跨平台分发）。
/// Suppress console/terminal window (cross-platform dispatch).
///
/// Windows → CREATE_NO_WINDOW；Linux/macOS → no-op。
pub fn suppress_console_window(cmd: &mut Command) {
    platform_impl::suppress_console_window(cmd);
}

/// 设置进程组（跨平台分发）。
/// Set process group (cross-platform dispatch).
///
/// Linux/macOS → process_group(0)；Windows → no-op（Job Object 替代）。
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
///
/// 注意：Windows 主 kill 路径不再调用此函数（由 JobHandle::drop() 处理），
/// 但保留为 utility 供手动调用场景。
/// Note: Windows main kill path no longer calls this (handled by JobHandle::drop()),
/// but kept as a utility for manual invocation.
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

// ============================================================================
// 守护进程孤儿保护 / Guardian Process Orphan Protection
// ============================================================================

/// Fork 守护进程，监控父进程存活状态，父进程死亡时 kill 子进程组。
/// Fork a guardian process to monitor parent liveness; kill child process group on parent death.
///
/// child_pgid: 子进程的进程组 ID（等于子进程 PID，由 process_group(0) 设置）。
/// child_pgid: Child process group ID (equals child PID, set by process_group(0)).
///
/// Windows 上此函数为空（Job Object 已处理孤儿保护）。
/// On Windows this is a no-op (Job Object already handles orphan protection).
#[cfg(any(target_os = "linux", target_os = "macos"))]
pub fn spawn_orphan_guardian(child_pgid: u32) -> Result<(), String> {
    platform_impl::spawn_orphan_guardian(child_pgid)
}
