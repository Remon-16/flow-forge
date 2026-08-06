import { open, save } from '@tauri-apps/plugin-dialog'
import { exists as tauriExists } from '@tauri-apps/plugin-fs'
import { invoke } from '@tauri-apps/api/core'

export interface FileEntry {
  name: string
  path: string
  isDirectory: boolean
  children?: FileEntry[]
}

const isDesktop = typeof window !== 'undefined' && !!(window as any).__TAURI_INTERNALS__

export async function openFileDialog(
  filtersOrMultiple?: { name: string; extensions: string[] }[] | boolean,
): Promise<string | string[] | null> {
  const multiple = typeof filtersOrMultiple === 'boolean' ? filtersOrMultiple : false
  const filters = typeof filtersOrMultiple === 'boolean' ? undefined : filtersOrMultiple

  if (isDesktop) {
    const selected = await open({ filters, multiple })
    if (multiple && Array.isArray(selected)) {
      return selected
    }
    return selected ?? null
  }

  // Browser fallback
  return new Promise((resolve) => {
    const input = document.createElement('input')
    input.type = 'file'
    input.multiple = multiple
    if (filters) {
      const extList = filters.flatMap((f) => f.extensions.map((e) => `.${e}`))
      input.accept = extList.join(',')
    }
    input.onchange = () => {
      if (multiple) {
        const names = Array.from(input.files || []).map(f => (f as any).path || f.name)
        if (names.length === 0) { resolve(null); return }
        resolve(names.join(';'))
        return
      }
      const file = input.files?.[0]
      if (!file) { resolve(null); return }
      const reader = new FileReader()
      reader.onload = () => {
        ;(input as any)._result = { name: file.name, data: reader.result }
        resolve(file.name)
      }
      reader.readAsArrayBuffer(file)
    }
    input.oncancel = () => resolve(null)
    input.click()
  })
}

export async function openDirectoryDialog(): Promise<string | null> {
  if (isDesktop) {
    const selected = await open({ directory: true })
    return selected ?? null
  }
  throw new Error('Directory selection is not supported in browser mode. Please use the desktop app.')
}

export async function saveFileDialog(
  options?: { defaultPath?: string; filters?: { name: string; extensions: string[] }[] },
): Promise<string | null> {
  if (isDesktop) {
    const selected = await save(options)
    return selected ?? null
  }
  throw new Error('Save dialog is not supported in browser mode. Please use the desktop app.')
}

export async function readFile(filePath: string): Promise<string> {
  if (isDesktop) return invoke<string>('read_file_text', { path: filePath })
  throw new Error('Direct file reading is not supported in browser mode. Please use "Open File" instead.')
}

export async function readFileBuffer(filePath: string): Promise<ArrayBuffer> {
  if (isDesktop) {
    const data = await invoke<number[]>('read_file_bytes', { path: filePath })
    return new Uint8Array(data).buffer as ArrayBuffer
  }
  throw new Error('Direct file reading is not supported in browser mode.')
}

export async function writeFile(filePath: string, content: string): Promise<void> {
  if (isDesktop) return invoke<void>('write_file_text', { path: filePath, content })
  throw new Error('Direct file writing is not supported in browser mode. Please use "Save As" instead.')
}

export async function writeFileBuffer(filePath: string, buffer: ArrayBuffer): Promise<void> {
  if (isDesktop) return invoke<void>('write_file_bytes', { path: filePath, data: Array.from(new Uint8Array(buffer)) })
  throw new Error('Direct file writing is not supported in browser mode.')
}

export async function readDirectory(dirPath: string): Promise<FileEntry[]> {
  if (isDesktop) return invoke<FileEntry[]>('read_dir_recursive', { dirPath })
  throw new Error('Directory reading is not supported in browser mode.')
}

export async function exists(filePath: string): Promise<boolean> {
  if (isDesktop) return tauriExists(filePath)
  return false
}

/**
 * 使用自定义 Tauri 命令检查文件是否存在（不受 plugin-fs scope 限制）。
 * Check file existence using custom Tauri command (not limited by plugin-fs scope).
 *
 * 使用轻量的 path_exists 命令（std::path::Path::exists），不再读取文件内容。
 * Uses lightweight path_exists command (std::path::Path::exists), no longer reads file content.
 * 相比旧实现（读取整个文件判断存在性），性能大幅提升。
 * Much faster than the old implementation (reading entire file to check existence).
 */
export async function fileExists(filePath: string): Promise<boolean> {
  if (!isDesktop) return false
  try {
    return await invoke<boolean>('path_exists', { path: filePath })
  } catch {
    return false
  }
}

export async function mkdir(dirPath: string): Promise<void> {
  if (isDesktop) {
    // 使用自定义 create_dir 命令（std::fs::create_dir_all），不受 plugin-fs scope 限制。
    // Use custom create_dir command (std::fs::create_dir_all), no plugin-fs scope restrictions.
    await invoke<void>('create_dir', { path: dirPath })
  }
}

export function getPlatform(): string {
  if (isDesktop) {
    return 'desktop'
  }
  return 'browser'
}

let _cachedOsPlatform: string | null = null

/**
 * 获取当前 OS 平台标识（从 Rust 后端获取，准确可靠）。
 * Get current OS platform identifier from Rust backend (accurate and reliable).
 * 返回值 / Returns: "windows" | "macos" | "linux"
 * 浏览器模式下回退为 navigator.platform / Falls back to navigator.platform in browser mode.
 */
export async function getOsPlatform(): Promise<string> {
  if (_cachedOsPlatform) return _cachedOsPlatform
  if (isDesktop) {
    _cachedOsPlatform = await invoke<string>('get_os_platform')
  } else {
    _cachedOsPlatform = (typeof navigator !== 'undefined' ? navigator.platform : '') || 'unknown'
  }
  return _cachedOsPlatform
}

export async function listDirectoryAll(dirPath: string): Promise<FileEntry[]> {
  if (isDesktop) return invoke<FileEntry[]>('list_dir_all', { dirPath })
  throw new Error('Directory listing is not supported in browser mode.')
}

export async function renameFile(oldPath: string, newPath: string): Promise<void> {
  if (isDesktop) return invoke<void>('rename_file', { oldPath, newPath })
  throw new Error('File renaming is not supported in browser mode.')
}

export async function deleteToTrash(path: string): Promise<void> {
  if (isDesktop) return invoke<void>('delete_to_trash', { path })
  throw new Error('File deletion is not supported in browser mode.')
}

export async function copyFileOrDir(from: string, to: string): Promise<void> {
  if (isDesktop) return invoke<void>('copy_file_or_dir', { from, to })
  throw new Error('File copy is not supported in browser mode.')
}

export async function moveFileOrDir(from: string, to: string): Promise<void> {
  if (isDesktop) return invoke<void>('move_file_or_dir', { from, to })
  throw new Error('File move is not supported in browser mode.')
}

export async function openInExplorer(path: string): Promise<void> {
  if (isDesktop) return invoke<void>('open_in_explorer', { path })
  throw new Error('Open in explorer is not supported in browser mode.')
}

export { isDesktop }
