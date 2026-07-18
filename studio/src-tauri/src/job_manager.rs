// Windows Job Object 句柄 — 父进程退出或句柄释放时自动终止 Job 内所有子进程。
// Windows Job Object handle — auto-terminate all processes in the Job when handle is closed.
//
// 每个子进程拥有独立的 JobHandle。当 ProcessHandle 被 drop（任务终止或应用退出），
// JobHandle::drop() 调用 CloseHandle，OS 通过 KILL_ON_JOB_CLOSE 强制终止 Job 内所有进程。
// Each subprocess owns its own JobHandle. When the ProcessHandle is dropped (task kill or
// app exit), JobHandle::drop() calls CloseHandle, and the OS forcibly terminates all
// processes in that Job via KILL_ON_JOB_CLOSE.
//
// 原理：Windows Job Object 递归追踪 Job 内所有进程及其后代进程。即使中间进程（如
// conda.exe→python.exe）已退出，孙子进程仍在 Job 中。KILL_ON_JOB_CLOSE 由 OS 内核
// 强制执行，比用户态工具（taskkill）更可靠。
// Principle: Windows Job Objects recursively track all processes spawned within the job,
// including descendants. Even if an intermediate process (e.g. conda.exe→python.exe) exits,
// grandchild processes remain in the job. KILL_ON_JOB_CLOSE is enforced by the OS kernel
// and is more reliable than user-mode tools like taskkill.

// Windows FFI 类型与常量 / Windows FFI types and constants
#[cfg(target_os = "windows")]
#[allow(non_camel_case_types, dead_code)]
mod win32 {
    pub type BOOL = i32;
    pub type HANDLE = isize;
    pub type DWORD = u32;
    pub type ULONG_PTR = usize;
    pub type SIZE_T = usize;
    pub type LPVOID = *mut std::ffi::c_void;

    pub const JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE: DWORD = 0x2000;
    pub const JOB_OBJECT_EXTENDED_LIMIT_INFORMATION: i32 = 9;

    #[repr(C)]
    pub struct JOBOBJECT_BASIC_LIMIT_INFORMATION {
        pub per_process_user_time_limit: i64,
        pub per_job_user_time_limit: i64,
        pub limit_flags: DWORD,
        pub minimum_working_set_size: SIZE_T,
        pub maximum_working_set_size: SIZE_T,
        pub active_process_limit: DWORD,
        pub affinity: ULONG_PTR,
        pub priority_class: DWORD,
        pub scheduling_class: DWORD,
    }

    #[repr(C)]
    pub struct IO_COUNTERS {
        pub read_operation_count: u64,
        pub write_operation_count: u64,
        pub other_operation_count: u64,
        pub read_transfer_count: u64,
        pub write_transfer_count: u64,
        pub other_transfer_count: u64,
    }

    #[repr(C)]
    pub struct JOBOBJECT_EXTENDED_LIMIT_INFORMATION {
        pub basic_limit_information: JOBOBJECT_BASIC_LIMIT_INFORMATION,
        pub io_info: IO_COUNTERS,
        pub process_memory_limit: SIZE_T,
        pub job_memory_limit: SIZE_T,
        pub peak_process_memory_used: SIZE_T,
        pub peak_job_memory_used: SIZE_T,
    }

    #[link(name = "kernel32")]
    extern "system" {
        pub fn CreateJobObjectW(
            lpJobAttributes: LPVOID,
            lpName: *const u16,
        ) -> HANDLE;

        pub fn SetInformationJobObject(
            hJob: HANDLE,
            jobObjectInfoClass: i32,
            lpJobObjectInfo: LPVOID,
            cbJobObjectInfoLength: DWORD,
        ) -> BOOL;

        pub fn AssignProcessToJobObject(
            hJob: HANDLE,
            hProcess: HANDLE,
        ) -> BOOL;

        pub fn CloseHandle(
            hObject: HANDLE,
        ) -> BOOL;
    }
}

/// 单个任务的 Windows Job Object 句柄。
/// Per-task Windows Job Object handle.
///
/// 创建时设置 KILL_ON_JOB_CLOSE，drop 时关闭句柄触发 OS 终止所有 Job 内进程。
/// Created with KILL_ON_JOB_CLOSE; closing the handle on drop triggers OS termination.
pub struct JobHandle {
    /// Windows Job Object HANDLE（非 Windows 平台不分配）。
    /// Windows Job Object HANDLE (not allocated on non-Windows).
    #[cfg(target_os = "windows")]
    handle: win32::HANDLE,
}

impl JobHandle {
    /// 创建新的 Job Object 并设置 KILL_ON_JOB_CLOSE 策略。
    /// Create a new Job Object with KILL_ON_JOB_CLOSE policy.
    ///
    /// 返回 None 表示创建失败（此时回退到 taskkill 方式终止进程）。
    /// Returns None on failure (fall back to taskkill-based process termination).
    pub fn new() -> Option<Self> {
        #[cfg(target_os = "windows")]
        {
            use std::ptr;
            use win32::*;

            unsafe {
                // 创建 Job Object / Create Job Object
                let handle = CreateJobObjectW(ptr::null_mut(), ptr::null());
                if handle == 0 {
                    // 创建失败不影响应用运行，子进程管理回退到 taskkill 方式
                    // Creation failure is non-fatal; fall back to taskkill-based cleanup
                    log::warn!("[JobHandle] CreateJobObjectW failed, will rely on taskkill fallback");
                    return None;
                }

                // 设置扩展限制信息 / Set extended limit info
                let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
                info.basic_limit_information.limit_flags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;

                let result = SetInformationJobObject(
                    handle,
                    JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                    &mut info as *mut _ as LPVOID,
                    std::mem::size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as DWORD,
                );
                if result == 0 {
                    log::warn!("[JobHandle] SetInformationJobObject failed, will rely on taskkill fallback");
                    CloseHandle(handle);
                    return None;
                }

                log::debug!("[JobHandle] created successfully");
                Some(Self { handle })
            }
        }

        #[cfg(not(target_os = "windows"))]
        {
            // 非 Windows 平台：Job Object 不可用，始终返回 None
            // Non-Windows: Job Object not available, always return None
            None
        }
    }

    /// 将进程分配给此 Job Object。
    /// Assign a process to this Job Object.
    /// `pid` 是进程 ID / `pid` is the process ID.
    pub fn assign(&self, _pid: u32) {
        #[cfg(target_os = "windows")]
        {
            use win32::*;

            if self.handle == 0 {
                return; // Job 未初始化，跳过 / Job not initialized, skip
            }

            unsafe {
                // 通过 PID 打开进程句柄 / Open process handle by PID
                // PROCESS_SET_QUOTA = 0x0100, PROCESS_TERMINATE = 0x0001
                const PROCESS_SET_QUOTA_AND_TERMINATE: DWORD = 0x0100 | 0x0001;
                let h_process = OpenProcess(PROCESS_SET_QUOTA_AND_TERMINATE, 0, _pid);
                if h_process == 0 {
                    // 进程可能在打开前已退出 / Process may have exited before we could open it
                    log::debug!("[JobHandle] OpenProcess failed for PID {} (process may have exited)", _pid);
                    return;
                }

                let result = AssignProcessToJobObject(self.handle, h_process);
                if result == 0 {
                    // 分配失败不影响应用（进程可能已退出或被其他 Job 管理）
                    // Assignment failure is non-fatal (process may have exited or be in another job)
                    log::warn!("[JobHandle] AssignProcessToJobObject failed for PID {} (may already be in another job)", _pid);
                } else {
                    log::debug!("[JobHandle] assigned PID {} to job", _pid);
                }

                CloseHandle(h_process);
            }
        }
    }
}

impl Drop for JobHandle {
    fn drop(&mut self) {
        #[cfg(target_os = "windows")]
        {
            use win32::*;
            if self.handle != 0 {
                log::debug!("[JobHandle] dropping — OS will terminate all processes in this job");
                unsafe { CloseHandle(self.handle); }
            }
        }
    }
}

// Windows 额外 FFI：OpenProcess
#[cfg(target_os = "windows")]
extern "system" {
    fn OpenProcess(
        dwDesiredAccess: win32::DWORD,
        bInheritHandle: win32::BOOL,
        dwProcessId: win32::DWORD,
    ) -> win32::HANDLE;
}
