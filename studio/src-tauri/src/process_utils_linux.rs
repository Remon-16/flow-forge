// Linux 平台进程管理实现。
// Linux platform process management implementation.
//
// 本文件仅在 Linux 编译。提供进程组管理 + prctl 守护进程孤儿保护。
// Compiled only on Linux. Provides process group management + prctl guardian orphan protection.
//
// 策略：守护进程（Guardian Process）
// Strategy: Guardian Process
//   每个子进程 spawn 时 fork 一个守护进程。守护进程监控父进程（studio）存活状态，
//   父进程死亡时执行 kill -9 -PGID 清理整棵进程树。
//   A guardian is forked per child process. It monitors the parent (studio) liveness
//   and kills the entire process group via kill -9 -PGID when the parent dies.
//
// 所有平台差异集中于此文件，业务代码无 #[cfg]。
// All platform differences are isolated here; business code has no #[cfg].

use std::process::{Child, Command};
use std::os::unix::process::CommandExt;

// ============================================================================
// Spawn 配置 / Spawn configuration
// ============================================================================

/// Linux GUI 应用启动的子进程默认不创建终端窗口，无需特殊处理。
/// Child processes from Linux GUI apps don't create terminal windows by default — no-op.
pub fn suppress_console_window(_cmd: &mut Command) {
    // no-op
}

/// 设置进程组，使子进程及其后代在同一组中，便于 kill -9 -PGID 整体终止。
/// Set process group so child + descendants are in one group for tree kill via kill -9 -PGID.
pub fn apply_process_group(cmd: &mut Command) {
    cmd.process_group(0);
}

// ============================================================================
// Kill / 终止
// ============================================================================

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

// ============================================================================
// 守护进程（Guardian Process）/ 孤儿保护
// ============================================================================

/// Fork 守护进程，监控父进程存活状态。
/// Fork a guardian process to monitor parent liveness.
///
/// child_pgid: 子进程的进程组 ID（等于子进程 PID，由 process_group(0) 设置）。
/// child_pgid: Child process group ID (equals child PID, set by process_group(0)).
///
/// 守护进程逻辑 / Guardian logic:
///   1. 设置 prctl(PR_SET_PDEATHSIG, SIGTERM) 让内核在父进程死亡时发送信号
///   2. 轮询 getppid() 检测父进程是否退出
///   3. 轮询 kill(-pgid, 0) 检测子进程是否已退出（正常完成）
///   4. 父进程死亡 → kill(-pgid, SIGKILL) 清理整棵进程树 → 退出
///   5. 子进程退出 → 守护进程自然退出
pub fn spawn_orphan_guardian(child_pgid: u32) -> Result<(), String> {
    // PR_SET_PDEATHSIG = 1, SIGTERM = 15
    const PR_SET_PDEATHSIG: i32 = 1;
    const SIGTERM: i32 = 15;
    const SIGKILL: i32 = 9;

    match unsafe { libc::fork() } {
        -1 => Err(format!(
            "guardian fork failed: {}",
            std::io::Error::last_os_error()
        )),
        0 => {
            // ================================================================
            // 守护进程 (子进程) / Guardian process (child)
            // ================================================================

            // 1. 设置父进程死亡信号 — 父进程死亡时内核自动发送 SIGTERM 到此守护进程
            //    Set parent death signal — kernel auto-delivers SIGTERM when parent dies
            unsafe {
                libc::prctl(PR_SET_PDEATHSIG, SIGTERM, 0, 0, 0);
            }

            let parent_pid = unsafe { libc::getppid() };

            // 2. 轮询：父进程存活 + 子进程组存在
            //    Poll: parent alive + child process group exists
            loop {
                // 父进程死亡？/ Parent died?
                if unsafe { libc::getppid() } != parent_pid {
                    // kill 整个进程组（含 conda, python, 所有后代）
                    // Kill entire process group (conda, python, all descendants)
                    unsafe {
                        libc::kill(-(child_pgid as i32), SIGKILL);
                    }
                    std::process::exit(0);
                }

                // 子进程组已退出？（正常完成）/ Child process group gone? (normal completion)
                // kill(pid, 0) 是 POSIX 权限检查技巧：信号 0 不发送信号，仅检查进程是否存在
                // kill(pid, 0) is a POSIX permission check trick: signal 0 only checks existence
                if unsafe { libc::kill(-(child_pgid as i32), 0) } != 0 {
                    std::process::exit(0);
                }

                std::thread::sleep(std::time::Duration::from_millis(200));
            }
        }
        _ => {
            // ================================================================
            // 父进程 (studio) / Parent process (studio)
            // ================================================================
            // 守护进程已 fork，父进程继续 spawn Python。
            // Guardian forked; parent continues to spawn Python.
            Ok(())
        }
    }
}
