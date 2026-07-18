use serde::Serialize;
use std::fs;
use std::io::{BufRead, BufReader};
use std::path::Path;
use std::process::{Command, Stdio};
use std::thread;
use tauri::{
    menu::{MenuBuilder, MenuItem},
    tray::TrayIconBuilder,
    AppHandle, Emitter, Manager, State, WindowEvent,
};

mod agent_manager;
use agent_manager::{AgentHandle, AgentManager};

#[derive(Serialize, Clone)]
#[serde(rename_all = "camelCase")]
struct FileEntry {
    name: String,
    path: String,
    is_directory: bool,
    children: Option<Vec<FileEntry>>,
}

#[tauri::command]
fn read_file_text(path: String) -> Result<String, String> {
    std::fs::read_to_string(&path).map_err(|e| e.to_string())
}

#[tauri::command]
fn write_file_text(path: String, content: String) -> Result<(), String> {
    std::fs::write(&path, &content).map_err(|e| e.to_string())
}

#[tauri::command]
fn read_file_bytes(path: String) -> Result<Vec<u8>, String> {
    std::fs::read(&path).map_err(|e| e.to_string())
}

#[tauri::command]
fn write_file_bytes(path: String, data: Vec<u8>) -> Result<(), String> {
    std::fs::write(&path, &data).map_err(|e| e.to_string())
}

/// 创建目录（递归），替代受 scope 限制的 plugin-fs mkdir。
/// Create directory recursively, replacing scope-restricted plugin-fs mkdir.
#[tauri::command]
fn create_dir(path: String) -> Result<(), String> {
    std::fs::create_dir_all(&path).map_err(|e| e.to_string())
}

#[tauri::command]
fn read_dir_recursive(dir_path: String) -> Result<Vec<FileEntry>, String> {
    fn walk(dir: &Path) -> Result<Vec<FileEntry>, String> {
        let mut entries = Vec::new();
        let read_dir = fs::read_dir(dir).map_err(|e| e.to_string())?;

        for entry in read_dir {
            let entry = entry.map_err(|e| e.to_string())?;
            let file_name = entry.file_name().to_string_lossy().to_string();

            if file_name.starts_with('.') || file_name == "node_modules" {
                continue;
            }

            let path = entry.path();
            let is_dir = path.is_dir();

            let children = if is_dir {
                Some(walk(&path)?)
            } else {
                None
            };

            let ext = path
                .extension()
                .map(|e| e.to_string_lossy().to_lowercase())
                .unwrap_or_default();

            if !is_dir && ext != "yaml" && ext != "yml" {
                continue;
            }

            entries.push(FileEntry {
                name: file_name,
                path: path.to_string_lossy().to_string(),
                is_directory: is_dir,
                children,
            });
        }

        Ok(entries)
    }

    walk(Path::new(&dir_path))
}

#[tauri::command]
fn rename_file(old_path: String, new_path: String) -> Result<(), String> {
    std::fs::rename(&old_path, &new_path).map_err(|e| e.to_string())
}

#[tauri::command]
fn delete_to_trash(path: String) -> Result<(), String> {
    trash::delete(&path).map_err(|e| e.to_string())
}

fn copy_dir_recursive(src: &Path, dst: &Path) -> Result<(), String> {
    fs::create_dir_all(dst).map_err(|e| e.to_string())?;
    let read_dir = fs::read_dir(src).map_err(|e| e.to_string())?;
    for entry in read_dir {
        let entry = entry.map_err(|e| e.to_string())?;
        let file_name = entry.file_name();
        let src_path = entry.path();
        let dst_path = dst.join(&file_name);
        if src_path.is_dir() {
            copy_dir_recursive(&src_path, &dst_path)?;
        } else {
            fs::copy(&src_path, &dst_path).map_err(|e| e.to_string())?;
        }
    }
    Ok(())
}

#[tauri::command]
fn copy_file_or_dir(from: String, to: String) -> Result<(), String> {
    let src = Path::new(&from);
    let dst = Path::new(&to);
    if src.is_dir() {
        copy_dir_recursive(src, dst)
    } else {
        std::fs::copy(src, dst).map_err(|e| e.to_string())?;
        Ok(())
    }
}

#[tauri::command]
fn move_file_or_dir(from: String, to: String) -> Result<(), String> {
    std::fs::rename(&from, &to).map_err(|e| e.to_string())
}

#[tauri::command]
fn open_in_explorer(path: String) -> Result<(), String> {
    #[cfg(target_os = "windows")]
    {
        std::process::Command::new("explorer")
            .arg("/select,")
            .arg(&path)
            .spawn()
            .map_err(|e| e.to_string())?;
    }
    #[cfg(target_os = "macos")]
    {
        std::process::Command::new("open")
            .arg("-R")
            .arg(&path)
            .spawn()
            .map_err(|e| e.to_string())?;
    }
    #[cfg(target_os = "linux")]
    {
        let parent = Path::new(&path).parent().unwrap_or(Path::new(&path));
        std::process::Command::new("xdg-open")
            .arg(parent)
            .spawn()
            .map_err(|e| e.to_string())?;
    }
    Ok(())
}

#[tauri::command]
fn list_dir_all(dir_path: String) -> Result<Vec<FileEntry>, String> {
    fn walk(dir: &Path) -> Result<Vec<FileEntry>, String> {
        let mut entries = Vec::new();
        let read_dir = fs::read_dir(dir).map_err(|e| e.to_string())?;

        for entry in read_dir {
            let entry = entry.map_err(|e| e.to_string())?;
            let file_name = entry.file_name().to_string_lossy().to_string();

            if file_name.starts_with('.') || file_name == "node_modules" {
                continue;
            }

            let path = entry.path();
            let is_dir = path.is_dir();

            let children = if is_dir {
                Some(walk(&path)?)
            } else {
                None
            };

            entries.push(FileEntry {
                name: file_name,
                path: path.to_string_lossy().to_string(),
                is_directory: is_dir,
                children,
            });
        }

        Ok(entries)
    }

    walk(Path::new(&dir_path))
}

// ============================================================================
// Agent subprocess commands / Agent 子进程命令
// ============================================================================

#[derive(Clone, Serialize)]
struct AgentLinePayload {
    task_id: String,
    line: String,
}

/// 通用 Python 子进程启动函数 — 被 spawn_agent / spawn_executor / spawn_converter 复用。
/// Generic Python process spawner — shared by agent, executor, and converter commands.
fn _spawn_python_process(
    app: &AppHandle,
    state: &AgentManager,
    task_id: &str,
    working_dir: &str,
    python_exe: &str,
    pre_args: &[String],
    args: &[String],
    stdout_event: &str,
    stderr_event: &str,
) -> Result<(), String> {
    // 启动子进程 / Spawn the subprocess
    // 构建命令：先添加前置参数（如 conda run -n env python），再添加主参数
    // Build command: pre_args first (e.g. conda run -n env python), then main args
    let mut cmd = Command::new(python_exe);
    cmd.args(pre_args);
    cmd.args(args);

    // Windows: 禁止创建 CMD 窗口 / Suppress console window creation
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x08000000); // CREATE_NO_WINDOW
    }

    let mut child = cmd
        .current_dir(working_dir)
        .stdout(Stdio::piped())
        .stdin(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("Failed to spawn process: {}", e))?;

    let stdin = child.stdin.take()
        .ok_or_else(|| "Failed to open stdin".to_string())?;

    // stdout 后台读取线程 / stdout background reader thread
    let stdout = child.stdout.take()
        .ok_or_else(|| "Failed to open stdout".to_string())?;
    let app_stdout = app.clone();
    let tid_stdout = task_id.to_string();
    let evt_stdout = stdout_event.to_string();
    thread::spawn(move || {
        let reader = BufReader::new(stdout);
        for line in reader.lines() {
            match line {
                Ok(l) => {
                    let _ = app_stdout.emit(&evt_stdout,
                        AgentLinePayload { task_id: tid_stdout.clone(), line: l });
                }
                Err(_) => break,
            }
        }
    });

    // stderr 后台读取线程 / stderr background reader thread
    let stderr = child.stderr.take()
        .ok_or_else(|| "Failed to open stderr".to_string())?;
    let app_stderr = app.clone();
    let tid_stderr = task_id.to_string();
    let evt_stderr = stderr_event.to_string();
    thread::spawn(move || {
        let reader = BufReader::new(stderr);
        for line in reader.lines() {
            match line {
                Ok(l) => {
                    let _ = app_stderr.emit(&evt_stderr,
                        AgentLinePayload { task_id: tid_stderr.clone(), line: l });
                }
                Err(_) => break,
            }
        }
    });

    // 存储进程句柄 / Store process handle
    state.insert(task_id.to_string(), AgentHandle { child, stdin })?;

    Ok(())
}

/// 检查是否有 agent 子进程在运行。
/// Check whether any agent subprocess is running.
#[tauri::command]
fn has_running_agents(
    state: State<'_, AgentManager>,
) -> Result<bool, String> {
    state.has_running()
}

/// 返回当前 OS 平台标识，用于前端跨平台路径解析。
/// Returns current OS platform identifier for cross-platform path resolution.
#[tauri::command]
fn get_os_platform() -> String {
    if cfg!(target_os = "windows") { "windows".into() }
    else if cfg!(target_os = "macos") { "macos".into() }
    else { "linux".into() }
}

/// 终止所有 agent 子进程并退出应用。
/// Kill all agent subprocesses and exit the app.
#[tauri::command]
fn force_quit_app(
    state: State<'_, AgentManager>,
    app: AppHandle,
) -> Result<(), String> {
    // 终止所有 agent / Kill all agents
    state.kill_all()?;
    // 退出应用 / Exit the app
    app.exit(0);
    Ok(())
}

#[tauri::command]
fn spawn_agent(
    app: AppHandle,
    state: State<'_, AgentManager>,
    task_id: String,
    working_dir: String,
    python_exe: String,
    pre_args: Vec<String>,
    args: Vec<String>,
) -> Result<(), String> {
    // 构建完整的命令行参数 / Build full command-line args
    // argv: [python_exe, ...pre_args, main.py, --studio, ...user_args]
    let mut full_args: Vec<String> = vec![
        "main.py".to_string(),
        "--studio".to_string(),
    ];
    full_args.extend(args);

    _spawn_python_process(
        &app, &state, &task_id, &working_dir, &python_exe,
        &pre_args, &full_args, "agent-stdout", "agent-stderr",
    )
}

// ============================================================================
// Executor subprocess commands / 执行器子进程命令
// ============================================================================

#[tauri::command]
fn spawn_executor(
    app: AppHandle,
    state: State<'_, AgentManager>,
    task_id: String,
    working_dir: String,
    python_exe: String,
    pre_args: Vec<String>,
    args: Vec<String>,
) -> Result<(), String> {
    // 执行器直接使用传入的 args，前端负责构建完整的 CLI 参数
    // Executor uses args as-is; the frontend constructs the full CLI
    // argv: [python_exe, ...pre_args, main.py, --config, ..., --yamlFiles, ...]
    _spawn_python_process(
        &app, &state, &task_id, &working_dir, &python_exe,
        &pre_args, &args, "executor-stdout", "executor-stderr",
    )
}

// ============================================================================
// Converter subprocess commands / 转换器子进程命令
// ============================================================================

#[tauri::command]
fn spawn_converter(
    app: AppHandle,
    state: State<'_, AgentManager>,
    task_id: String,
    working_dir: String,
    python_exe: String,
    pre_args: Vec<String>,
    args: Vec<String>,
) -> Result<(), String> {
    // 转换器直接使用传入的 args，前端负责构建完整的 CLI 参数
    // Converter uses args as-is; the frontend constructs the full CLI
    // argv: [python_exe, ...pre_args, converter_main.py, excel2yaml, --input, ..., --output, ...]
    _spawn_python_process(
        &app, &state, &task_id, &working_dir, &python_exe,
        &pre_args, &args, "converter-stdout", "converter-stderr",
    )
}

#[tauri::command]
fn send_to_agent(
    state: State<'_, AgentManager>,
    task_id: String,
    command: String,
) -> Result<(), String> {
    state.send_command(&task_id, &command)
}

#[tauri::command]
fn kill_agent(
    state: State<'_, AgentManager>,
    task_id: String,
) -> Result<(), String> {
    state.kill(&task_id)
}

#[tauri::command]
fn check_agent_running(
    state: State<'_, AgentManager>,
    task_id: String,
) -> Result<bool, String> {
    // 先尝试清理已退出的进程 / First try to clean up exited processes
    let code = state.cleanup(&task_id)?;
    match code {
        Some(c) if c < 0 => Ok(false),  // 未找到 / Not found
        Some(_) => Ok(false),            // 已退出 / Exited
        None => Ok(true),                // 仍运行 / Still running
    }
}

// ---- 执行器/转换器的 kill/check 复用 AgentManager，仅注册新命令名 / Executor/converter kill/check reuse AgentManager ----

#[tauri::command]
fn kill_executor(
    state: State<'_, AgentManager>,
    task_id: String,
) -> Result<(), String> {
    state.kill(&task_id)
}

#[tauri::command]
fn kill_converter(
    state: State<'_, AgentManager>,
    task_id: String,
) -> Result<(), String> {
    state.kill(&task_id)
}

#[tauri::command]
fn check_executor_running(
    state: State<'_, AgentManager>,
    task_id: String,
) -> Result<bool, String> {
    let code = state.cleanup(&task_id)?;
    match code {
        Some(c) if c < 0 => Ok(false),
        Some(_) => Ok(false),
        None => Ok(true),
    }
}

#[tauri::command]
fn check_converter_running(
    state: State<'_, AgentManager>,
    task_id: String,
) -> Result<bool, String> {
    let code = state.cleanup(&task_id)?;
    match code {
        Some(c) if c < 0 => Ok(false),
        Some(_) => Ok(false),
        None => Ok(true),
    }
}

// ============================================================================
// App entry point / 应用入口
// ============================================================================

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .manage(agent_manager::AgentManager::new())
        .setup(|app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }

            // 系统托盘 / System tray
            let show_item = MenuItem::with_id(app, "show", "显示 Flow Forge", true, None::<&str>)?;
            let quit_item = MenuItem::with_id(app, "quit", "退出", true, None::<&str>)?;
            let tray_menu = MenuBuilder::new(app)
                .items(&[&show_item, &quit_item])
                .build()?;

            TrayIconBuilder::with_id("main-tray")
                .icon(app.default_window_icon().unwrap().clone())
                .menu(&tray_menu)
                .show_menu_on_left_click(false)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "show" => {
                        if let Some(w) = app.get_webview_window("main") {
                            let _ = w.show();
                            let _ = w.unminimize();
                            let _ = w.set_focus();
                        }
                    }
                    "quit" => {
                        // 强制退出前终止所有 agent / Kill all agents before exit
                        if let Some(state) = app.try_state::<AgentManager>() {
                            let _ = state.kill_all();
                        }
                        app.exit(0);
                    }
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    // 左键点击显示窗口 / Left-click shows window
                    if let tauri::tray::TrayIconEvent::Click {
                        button: tauri::tray::MouseButton::Left,
                        button_state: tauri::tray::MouseButtonState::Up,
                        ..
                    } = event
                    {
                        let app = tray.app_handle();
                        if let Some(w) = app.get_webview_window("main") {
                            let _ = w.show();
                            let _ = w.unminimize();
                            let _ = w.set_focus();
                        }
                    }
                })
                .build(app)?;

            // 拦截窗口关闭事件，防止被托盘图标默认行为吞掉
            // Intercept window close event to prevent it from being swallowed by tray default behavior
            if let Some(window) = app.get_webview_window("main") {
                let app_handle = app.handle().clone();
                window.on_window_event(move |event| {
                    if let WindowEvent::CloseRequested { api, .. } = event {
                        // 阻止默认关闭/隐藏行为 / Prevent default close/hide behavior
                        api.prevent_close();
                        // 通知 JS 层弹出确认弹框 / Notify JS layer to show confirmation dialog
                        let _ = app_handle.emit("window-close-requested", ());
                    }
                });
            }

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            read_file_text,
            write_file_text,
            read_file_bytes,
            write_file_bytes,
            create_dir,
            read_dir_recursive,
            list_dir_all,
            rename_file,
            delete_to_trash,
            copy_file_or_dir,
            move_file_or_dir,
            open_in_explorer,
            get_os_platform,
            has_running_agents,
            force_quit_app,
            spawn_agent,
            send_to_agent,
            kill_agent,
            check_agent_running,
            spawn_executor,
            kill_executor,
            check_executor_running,
            spawn_converter,
            kill_converter,
            check_converter_running,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
