// Windows 平台进程管理实现。
// Windows platform process management implementation.
//
// 本文件仅在 Windows 编译。提供 taskkill 进程树终止、DETACHED_PROCESS 控制台抑制。
// Compiled only on Windows. Provides taskkill tree kill and DETACHED_PROCESS console suppression.
//
// 所有平台差异集中于此文件，业务代码无 #[cfg]。
// All platform differences are isolated here; business code has no #[cfg].

use std::process::{Child, Command};
use std::os::windows::process::CommandExt;

/// 禁止子进程弹出控制台窗口。
/// Suppress console window for child process.
///
/// DETACHED_PROCESS：不继承父进程控制台，比 CREATE_NO_WINDOW 对 Python CRT I/O 兼容性更好。
/// DETACHED_PROCESS: don't inherit parent console; better Python CRT I/O compatibility.
pub fn suppress_console_window(cmd: &mut Command) {
    cmd.creation_flags(0x00000008); // DETACHED_PROCESS
}

/// Windows 不需要进程组。
/// Windows doesn't need process groups.
///
/// taskkill /T 通过 ParentProcessId 枚举子进程，无需 PGID。
/// taskkill /T enumerates children via ParentProcessId; no PGID needed.
pub fn apply_process_group(_cmd: &mut Command) {
    // no-op
}

/// 使用 taskkill /F /T 终止整个进程树（含孙子进程）。
/// Kill entire process tree (including grandchildren) via taskkill /F /T.
///
/// 必须在 child.kill() 之前执行，否则父进程死后 taskkill 无法通过 ParentProcessId 枚举子进程。
/// Must run BEFORE child.kill(), or taskkill can't enumerate children after the parent dies.
pub fn kill_process_tree(child: &mut Child) {
    let pid = child.id();
    match Command::new("taskkill")
        .args(["/F", "/T", "/PID", &pid.to_string()])
        .output()
    {
        Ok(out) => {
            if !out.status.success() {
                let stderr = String::from_utf8_lossy(&out.stderr);
                log::warn!(
                    "[kill_process_tree] taskkill failed for PID {}: {}",
                    pid,
                    stderr.trim()
                );
            }
        }
        Err(e) => {
            log::warn!(
                "[kill_process_tree] taskkill spawn failed for PID {}: {}",
                pid,
                e
            );
        }
    }
}
