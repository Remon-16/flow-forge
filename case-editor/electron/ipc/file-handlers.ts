import { ipcMain } from 'electron'
import fsp from 'node:fs/promises'
import path from 'node:path'

export interface FileEntry {
  name: string
  path: string
  isDirectory: boolean
  children?: FileEntry[]
}

async function readDirectoryRecursive(dirPath: string): Promise<FileEntry[]> {
  const entries = await fsp.readdir(dirPath, { withFileTypes: true })
  const result: FileEntry[] = []

  for (const entry of entries) {
    // Skip hidden files and node_modules
    if (entry.name.startsWith('.') || entry.name === 'node_modules') continue

    const fullPath = path.join(dirPath, entry.name)
    const item: FileEntry = {
      name: entry.name,
      path: fullPath,
      isDirectory: entry.isDirectory(),
    }

    if (entry.isDirectory()) {
      item.children = await readDirectoryRecursive(fullPath)
    }

    // Only include directories and .yaml/.yml files
    if (entry.isDirectory() || /\.ya?ml$/i.test(entry.name)) {
      result.push(item)
    }
  }

  // Directories first, then files, alphabetical
  result.sort((a, b) => {
    if (a.isDirectory !== b.isDirectory) return a.isDirectory ? -1 : 1
    return a.name.localeCompare(b.name)
  })

  return result
}

export function registerFileHandlers() {
  ipcMain.handle('file:read', async (_event, filePath: string, encoding: string) => {
    return fsp.readFile(filePath, { encoding: encoding as BufferEncoding })
  })

  ipcMain.handle('file:readBuffer', async (_event, filePath: string) => {
    const buffer = await fsp.readFile(filePath)
    return buffer.buffer.slice(buffer.byteOffset, buffer.byteOffset + buffer.byteLength)
  })

  ipcMain.handle('file:write', async (_event, filePath: string, content: string) => {
    await fsp.mkdir(path.dirname(filePath), { recursive: true })
    await fsp.writeFile(filePath, content, 'utf-8')
  })

  ipcMain.handle('file:writeBuffer', async (_event, filePath: string, buffer: ArrayBuffer) => {
    await fsp.mkdir(path.dirname(filePath), { recursive: true })
    await fsp.writeFile(filePath, Buffer.from(buffer))
  })

  ipcMain.handle('file:readDirectory', async (_event, dirPath: string) => {
    return readDirectoryRecursive(dirPath)
  })

  ipcMain.handle('file:exists', async (_event, filePath: string) => {
    try {
      await fsp.access(filePath)
      return true
    } catch {
      return false
    }
  })

  ipcMain.handle('file:mkdir', async (_event, dirPath: string) => {
    await fsp.mkdir(dirPath, { recursive: true })
  })
}
