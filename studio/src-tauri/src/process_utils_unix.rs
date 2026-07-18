// Unix 平台进程管理实现（Linux / macOS / FreeBSD 等）。
// Unix platform process management implementation (Linux / macOS / FreeBSD etc.).
//
// 本文件仅在 Unix 系编译。提供 kill -9 -PGID 进程组终止、process_group(0) 设置。
// Compiled only on Unix-family targets. Provides kill -9 -PGID group kill and process_group(0).
//
// 所有平台差异集中于此文件，业务代码无 #[cfg]。
// All platform differences are isolated here; business code has no #[cfg].

use std::process::{Child, Command};
use std::os::unix::process::CommandExt;

/// Unix GUI 应用启动的子进程默认不创建终端窗口，无需特殊处理。
/// Child processes from Unix GUI apps don't create terminal windows by default — no-op.
pub fn suppress_console_window(_cmd: &mut Command) {
    // no-op
}

/// 设置进程组，使子进程及其后代在同一组中，便于 kill -9 -PGID 整体终止。
/// Set process group so child + descendants are in one group for tree kill via kill -9 -PGID.
pub fn apply_process_group(cmd: &mut Command) {
    cmd.process_group(0);
}

/// 使用 kill -9 -PGID 终止整个进程组。
/// Kill entire process group via kill -9 -PGID.
///
/// 必须在 child.kill() 之前执行，确保信号在组 leader 终止前发出到所有后代。
/// Must run BEFORE child.kill() so the signal reaches all descendants before the group leader dies.
pub fn kill_process_tree(child: &mut Child) {
    let pid = child.id();
    match Command::new("kill")
        .args(["-9", &format!("-{}", pid)])
        .output()
    {
        Ok(out) => {
            if !out.status.success() {
                let stderr = String::from_utf8_lossy(&out.stderr);
                log::warn!(
                    "[kill_process_tree] kill -9 -{} failed: {}",
                    pid,
                    stderr.trim()
                );
            }
        }
        Err(e) => {
            log::warn!(
                "[kill_process_tree] kill spawn failed for PID {}: {}",
                pid,
                e
            );
        }
    }
}
