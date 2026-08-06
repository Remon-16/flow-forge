// macOS 平台进程管理实现。
// macOS platform process management implementation.
//
// 本文件仅在 macOS 编译。提供进程组管理 + kqueue 守护进程孤儿保护。
// Compiled only on macOS. Provides process group management + kqueue guardian orphan protection.
//
// 策略：守护进程（Guardian Process）
// Strategy: Guardian Process
//   每个子进程 spawn 时 fork 一个守护进程。守护进程通过 kqueue 监控父进程（studio）存活状态，
//   父进程死亡时执行 kill -9 -PGID 清理整棵进程树。
//   A guardian is forked per child process. It monitors the parent (studio) liveness
//   via kqueue and kills the entire process group via kill -9 -PGID when the parent dies.
//
// 所有平台差异集中于此文件，业务代码无 #[cfg]。
// All platform differences are isolated here; business code has no #[cfg].

use std::process::{Child, Command};
use std::os::unix::process::CommandExt;

// macOS kqueue FFI — libc crate 不提供 macOS 特定的 kevent 结构体和常量。
// macOS kqueue FFI — the libc crate doesn't provide macOS-specific kevent struct & constants.
#[allow(non_camel_case_types)]
mod ffi {
    pub type c_int = i32;

    pub const EVFILT_PROC: i16 = -5;        // 进程事件过滤器 / Process event filter
    pub const NOTE_EXIT: u32 = 0x80000000;   // 进程退出通知 / Process exit notification
    pub const EV_ADD: u16 = 0x0001;          // 添加事件 / Add event
    pub const EV_ENABLE: u16 = 0x0004;       // 启用事件 / Enable event

    #[repr(C)]
    pub struct kevent {
        pub ident: usize,
        pub filter: i16,
        pub flags: u16,
        pub fflags: u32,
        pub data: isize,
        pub udata: *mut std::ffi::c_void,
    }

    #[repr(C)]
    pub struct timespec {
        pub tv_sec: isize,
        pub tv_nsec: isize,
    }

    extern "C" {
        pub fn kqueue() -> c_int;
        pub fn kevent(
            kq: c_int,
            changelist: *const kevent,
            nchanges: c_int,
            eventlist: *mut kevent,
            nevents: c_int,
            timeout: *const timespec,
        ) -> c_int;
    }
}

// ============================================================================
// Spawn 配置 / Spawn configuration
// ============================================================================

/// macOS GUI 应用启动的子进程默认不创建终端窗口，无需特殊处理。
/// Child processes from macOS GUI apps don't create terminal windows by default — no-op.
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

/// Fork 守护进程，使用 kqueue 监控父进程存活状态。
/// Fork a guardian process using kqueue to monitor parent liveness.
///
/// child_pgid: 子进程的进程组 ID（等于子进程 PID，由 process_group(0) 设置）。
/// child_pgid: Child process group ID (equals child PID, set by process_group(0)).
///
/// macOS 没有 prctl(PR_SET_PDEATHSIG)，使用 kqueue EVFILT_PROC + NOTE_EXIT 监控父进程。
/// macOS lacks prctl(PR_SET_PDEATHSIG); uses kqueue EVFILT_PROC + NOTE_EXIT instead.
pub fn spawn_orphan_guardian(child_pgid: u32) -> Result<(), String> {
    use ffi::*;

    let pgid_i32 = child_pgid as i32;

    match unsafe { libc::fork() } {
        -1 => Err(format!(
            "guardian fork failed: {}",
            std::io::Error::last_os_error()
        )),
        0 => {
            // ================================================================
            // 守护进程 (子进程) / Guardian process (child)
            // ================================================================

            let parent_pid = unsafe { libc::getppid() } as usize;

            // 1. 创建 kqueue / Create kqueue
            let kq = unsafe { kqueue() };
            if kq < 0 {
                // kqueue 创建失败 → 回退到轮询方式 / Fall back to polling
                guardian_poll_loop(parent_pid as u32, child_pgid);
            }

            // 2. 注册父进程 PID，监听 EVFILT_PROC + NOTE_EXIT
            //    Register parent PID with EVFILT_PROC + NOTE_EXIT
            let mut ev = kevent {
                ident: parent_pid,
                filter: EVFILT_PROC,
                flags: EV_ADD | EV_ENABLE,
                fflags: NOTE_EXIT,
                data: 0,
                udata: std::ptr::null_mut(),
            };

            let ret = unsafe {
                kevent(kq, &ev, 1, std::ptr::null_mut(), 0, std::ptr::null())
            };
            if ret < 0 {
                // kqueue 注册失败 → 回退到轮询方式 / Registration failed → fall back to polling
                guardian_poll_loop(parent_pid as u32, child_pgid);
            }

            // 3. 阻塞等待事件（父进程退出时 kevent 返回）
            //    Block waiting for event (kevent returns when parent exits)
            let mut ev_out: kevent = unsafe { std::mem::zeroed() };
            let _ = unsafe {
                kevent(kq, std::ptr::null(), 0, &mut ev_out, 1, std::ptr::null())
            };

            // 4. 父进程已退出 → kill 整个进程组 / Parent exited → kill entire process group
            unsafe {
                libc::kill(-pgid_i32, 9 /* SIGKILL */);
            }
            std::process::exit(0);
        }
        _ => {
            // ================================================================
            // 父进程 (studio) / Parent process (studio)
            // ================================================================
            Ok(())
        }
    }
}

/// 轮询回退（kqueue 创建/注册失败时使用）。
/// Polling fallback (used when kqueue creation/registration fails).
///
/// 逻辑与 Linux 守护进程相同：轮询 getppid() + kill(-pgid, 0)。
/// Same logic as Linux guardian: poll getppid() + kill(-pgid, 0).
fn guardian_poll_loop(parent_pid: u32, child_pgid: u32) -> ! {
    let pgid_i32 = child_pgid as i32;
    loop {
        if unsafe { libc::getppid() } != parent_pid {
            unsafe {
                libc::kill(-pgid_i32, 9 /* SIGKILL */);
            }
            std::process::exit(0);
        }
        // 子进程组已退出？/ Child process group exited?
        if unsafe { libc::kill(-pgid_i32, 0) } != 0 {
            std::process::exit(0);
        }
        std::thread::sleep(std::time::Duration::from_millis(200));
    }
}
