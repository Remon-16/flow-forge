import { open, save } from '@tauri-apps/plugin-dialog'
import { exists as tauriExists, mkdir as tauriMkdir } from '@tauri-apps/plugin-fs'
import { invoke } from '@tauri-apps/api/core'

export interface FileEntry {
  name: string
  path: string
  isDirectory: boolean
  children?: FileEntry[]
}

const isDesktop = typeof window !== 'undefined' && !!(window as any).__TAURI_INTERNALS__

export async function openFileDialog(
  filters?: { name: string; extensions: string[] }[],
): Promise<string | null> {
  if (isDesktop) {
    const selected = await open({ filters })
    return selected ?? null
  }

  // Browser fallback
  return new Promise((resolve) => {
    const input = document.createElement('input')
    input.type = 'file'
    if (filters) {
      const extList = filters.flatMap((f) => f.extensions.map((e) => `.${e}`))
      input.accept = extList.join(',')
    }
    input.onchange = () => {
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

export async function mkdir(dirPath: string): Promise<void> {
  if (isDesktop) {
    await tauriMkdir(dirPath, { recursive: true })
  }
}

export function getPlatform(): string {
  if (isDesktop) {
    // platform() returns a Promise, but we need synchronous behavior
    return 'desktop'
  }
  return 'browser'
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
