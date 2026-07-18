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
/// Windows: child.kill() + taskkill /F /T /PID
/// Unix:    child.kill() + kill -9 -PGID（进程组整体终止）
pub fn kill_process_tree(child: &mut Child) {
    let pid = child.id();

    // 终止直接子进程 / Kill the direct child process
    let _ = child.kill();
    // 非阻塞回收僵尸进程 / Non-blocking zombie reaping
    let _ = child.try_wait();

    // Windows: 使用 taskkill /T 终止整个进程树（含孙子进程）
    // Windows: kill the entire process tree (including grandchildren)
    #[cfg(target_os = "windows")]
    {
        let _ = Command::new("taskkill")
            .args(["/F", "/T", "/PID", &pid.to_string()])
            .output();
    }

    // Unix: 使用进程组终止所有后代（需要 spawn 时设置了 process_group(0)）
    // Unix: kill the entire process group (requires process_group(0) at spawn time)
    #[cfg(not(target_os = "windows"))]
    {
        let _ = Command::new("kill")
            .args(["-9", &format!("-{}", pid)])
            .output();
    }
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
