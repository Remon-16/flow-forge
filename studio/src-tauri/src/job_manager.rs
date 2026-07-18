// Windows Job Object 管理器 — 父进程退出时自动终止所有子进程。
// Windows Job Object manager — auto-terminate all child processes when parent exits.
//
// 原理：将每个子进程分配到 Windows Job Object，设置 JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE。
// 当 Tauri 进程以任何方式终止时（包括任务管理器强杀），OS 自动终止 Job 内所有进程。
// Principle: assign each child to a Job Object with KILL_ON_JOB_CLOSE flag.
// When the Tauri process exits for ANY reason (incl. Task Manager kill), the OS
// automatically terminates all processes in the Job.

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

/// 全局 Job Object 管理器。
/// Global Job Object manager.
pub struct JobManager {
    /// Windows Job Object HANDLE（非 Windows 平台不分配）。
    /// Windows Job Object HANDLE (not allocated on non-Windows).
    #[cfg(target_os = "windows")]
    handle: win32::HANDLE,
}

impl JobManager {
    /// 创建 Job Object 并设置 KILL_ON_JOB_CLOSE 策略。
    /// Create a Job Object with KILL_ON_JOB_CLOSE policy.
    pub fn new() -> Self {
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
                    log::warn!("[JobManager] CreateJobObjectW failed");
                    return Self { handle: 0 };
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
                    log::warn!("[JobManager] SetInformationJobObject failed");
                    CloseHandle(handle);
                    return Self { handle: 0 };
                }

                Self { handle }
            }
        }

        #[cfg(not(target_os = "windows"))]
        {
            Self {}
        }
    }

    /// 将进程分配给 Job Object。
    /// Assign a process to the Job Object.
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
                    return;
                }

                let result = AssignProcessToJobObject(self.handle, h_process);
                if result == 0 {
                    // 分配失败不影响应用（进程可能已退出或被其他 Job 管理）
                    // Assignment failure is non-fatal (process may have exited or be in another job)
                }

                CloseHandle(h_process);
            }
        }
    }
}

impl Drop for JobManager {
    fn drop(&mut self) {
        #[cfg(target_os = "windows")]
        {
            use win32::*;
            if self.handle != 0 {
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
