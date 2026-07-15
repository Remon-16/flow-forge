// Settings Store — File-based settings persistence for packaged EXE.
// 设置存储 — 用于 EXE 打包后的文件持久化。

import { isDesktop, readFile, writeFile, exists, mkdir } from './desktop-bridge'

const APP_NAME = 'flow-forge-studio'

let _appDataDir: string | null = null

/**
 * 获取应用数据目录路径。
 * Get the app data directory path.
 * Windows: %APPDATA%/flow-forge-studio/
 */
export async function getAppDataDir(): Promise<string> {
  if (_appDataDir) return _appDataDir

  if (isDesktop) {
    // 使用 Tauri path API 获取 app_data_dir
    // Use Tauri path API to get app_data_dir
    try {
      const { appDataDir } = await import('@tauri-apps/api/path')
      _appDataDir = await appDataDir()
      return _appDataDir!
    } catch {
      // Fallback: use APPDATA env var on Windows
      const home = (typeof process !== 'undefined' && process.env?.APPDATA)
        || (typeof window !== 'undefined' ? '' : '')
      _appDataDir = home ? `${home}/${APP_NAME}` : `./${APP_NAME}`
      return _appDataDir
    }
  }

  // Browser fallback: use localStorage, no file system
  return `/${APP_NAME}`
}

/**
 * 从文件加载设置。
 * Load settings from a JSON file. Returns defaults if file doesn't exist.
 */
export async function loadSettingsFile<T>(
  filename: string,
  defaults: T,
): Promise<T> {
  if (!isDesktop) {
    // Browser fallback: localStorage
    try {
      const raw = localStorage.getItem(`studio-${filename}`)
      if (raw) return JSON.parse(raw) as T
    } catch { /* ignore */ }
    return defaults
  }

  const dir = await getAppDataDir()
  const path = `${dir}/${filename}`

  if (!(await exists(path))) return defaults

  try {
    const raw = await readFile(path)
    return JSON.parse(raw) as T
  } catch {
    return defaults
  }
}

/**
 * 保存设置到文件。
 * Save settings to a JSON file.
 */
export async function saveSettingsFile<T>(
  filename: string,
  data: T,
): Promise<void> {
  if (!isDesktop) {
    // Browser fallback: localStorage
    localStorage.setItem(`studio-${filename}`, JSON.stringify(data))
    return
  }

  const dir = await getAppDataDir()
  const path = `${dir}/${filename}`

  // 确保目录存在 / Ensure directory exists
  if (!(await exists(dir))) {
    await mkdir(dir)
  }

  await writeFile(path, JSON.stringify(data, null, 2))
}
