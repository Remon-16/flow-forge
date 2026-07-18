// 进程工具模块 — 通用子进程操作函数，不耦合任何业务模块。
// Process utility module — general-purpose subprocess operations, decoupled from business logic.
//
// 提供跨平台的进程树终止能力。所有 kill 逻辑集中于此，业务代码只调用本模块的函数。
// Provides cross-platform process tree termination. All kill logic lives here;
// business code only calls functions from this module.

use std::io::Write;
use std::process::{Child, ChildStdin, Command};

// ============================================================================
// 跨平台 spawn 配置 / Cross-platform spawn configuration
// ============================================================================

/// 禁止子进程弹出控制台/终端窗口（跨平台）。
/// Suppress console/terminal window for child process (cross-platform).
///
/// Windows: 设置 CREATE_NO_WINDOW 标志，禁止 CMD 窗口弹出。
/// Windows: set CREATE_NO_WINDOW flag to prevent CMD window from appearing.
///
/// Unix (Linux/macOS): GUI 应用启动的子进程默认不会创建终端窗口，
/// 此处显式保留为 no-op 以表达跨平台意图，同时防止未来平台行为变更。
/// Unix: child processes from GUI apps don't create terminal windows by default;
/// kept as explicit no-op to express cross-platform intent and guard against future changes.
pub fn suppress_console_window(cmd: &mut Command) {
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x08000000); // CREATE_NO_WINDOW
    }
    #[cfg(not(target_os = "windows"))]
    {
        // Unix: 默认不弹窗，显式 no-op / Unix: no terminal window by default, explicit no-op
        let _ = cmd;
    }
}

/// 设置进程组，使子进程及其后代在同一组中，便于 kill_process_tree 整体终止。
/// Set process group so child + descendants are in one group for tree kill.
///
/// 仅 Unix 系统需要；Windows 使用 taskkill /T 实现进程树终止。
/// Only needed on Unix; Windows uses taskkill /T for process tree termination.
pub fn apply_process_group(cmd: &mut Command) {
    #[cfg(not(target_os = "windows"))]
    {
        use std::os::unix::process::CommandExt;
        cmd.process_group(0);
    }
    #[cfg(target_os = "windows")]
    {
        let _ = cmd;
    }
}

// ============================================================================
// Kill 函数 / Kill functions
// ============================================================================

/// 强制终止子进程及其所有后代进程（跨平台）。
/// Force-kill a child process and all its descendants (cross-platform).
///
/// Windows: taskkill /F /T /PID 先于 child.kill()，确保进程树在父进程存活时被枚举。
/// Unix:    kill -9 -PGID 先于 child.kill()，确保进程组信号在 leader 终止前发出。
///
/// 重要：必须先通过平台工具终止进程树，再 child.kill() 兜底。
/// 若先 child.kill() 再杀进程树，父进程已死后 taskkill 无法枚举子进程。
/// Windows: taskkill /F /T /PID BEFORE child.kill() — tree must be intact for enumeration.
/// Unix:    kill -9 -PGID BEFORE child.kill() — signal must reach group before leader dies.
pub fn kill_process_tree(child: &mut Child) {
    let pid = child.id();

    // Windows: 使用 taskkill /T 终止整个进程树（含孙子进程）
    // 必须在 child.kill() 之前执行，否则父进程已死无法枚举子进程。
    // Windows: kill entire process tree (including grandchildren) BEFORE child.kill(),
    // or the dead parent can't be found by taskkill to enumerate children.
    #[cfg(target_os = "windows")]
    {
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
                log::warn!("[kill_process_tree] taskkill spawn failed for PID {}: {}", pid, e);
            }
        }
    }

    // Unix: 使用进程组终止所有后代（需要 spawn 时设置了 process_group(0)）
    // 必须在 child.kill() 之前执行，确保信号在组 leader 终止前发出。
    // Unix: kill entire process group BEFORE child.kill(), so the signal reaches
    // all descendants while the group leader is still alive.
    #[cfg(not(target_os = "windows"))]
    {
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
                log::warn!("[kill_process_tree] kill spawn failed for PID {}: {}", pid, e);
            }
        }
    }

    // 兜底：终止直接子进程并回收僵尸（此时进程树已由上述平台工具处理）
    // Fallback: kill direct child and reap zombie (tree already handled above)
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
