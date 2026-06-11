import { contextBridge, ipcRenderer } from 'electron'

export interface FileEntry {
  name: string
  path: string
  isDirectory: boolean
  children?: FileEntry[]
}

export interface FileFilter {
  name: string
  extensions: string[]
}

export interface ElectronAPI {
  openFileDialog(options?: { filters?: FileFilter[]; defaultPath?: string }): Promise<string | null>
  openDirectoryDialog(defaultPath?: string): Promise<string | null>
  saveFileDialog(options?: { filters?: FileFilter[]; defaultPath?: string }): Promise<string | null>
  readFile(filePath: string, encoding?: string): Promise<string>
  readFileBuffer(filePath: string): Promise<ArrayBuffer>
  writeFile(filePath: string, content: string): Promise<void>
  writeFileBuffer(filePath: string, buffer: ArrayBuffer): Promise<void>
  readDirectory(dirPath: string): Promise<FileEntry[]>
  exists(filePath: string): Promise<boolean>
  mkdir(dirPath: string): Promise<void>
  getPlatform(): string
  getVersion(): string
  onMenuAction(callback: (action: string) => void): void
  removeMenuActionListener(): void
}

contextBridge.exposeInMainWorld('electronAPI', {
  openFileDialog: (options?: { filters?: FileFilter[]; defaultPath?: string }) =>
    ipcRenderer.invoke('dialog:openFile', options),

  openDirectoryDialog: (defaultPath?: string) =>
    ipcRenderer.invoke('dialog:openDirectory', defaultPath),

  saveFileDialog: (options?: { filters?: FileFilter[]; defaultPath?: string }) =>
    ipcRenderer.invoke('dialog:saveFile', options),

  readFile: (filePath: string, encoding = 'utf-8') =>
    ipcRenderer.invoke('file:read', filePath, encoding),

  readFileBuffer: (filePath: string) =>
    ipcRenderer.invoke('file:readBuffer', filePath),

  writeFile: (filePath: string, content: string) =>
    ipcRenderer.invoke('file:write', filePath, content),

  writeFileBuffer: (filePath: string, buffer: ArrayBuffer) =>
    ipcRenderer.invoke('file:writeBuffer', filePath, buffer),

  readDirectory: (dirPath: string) =>
    ipcRenderer.invoke('file:readDirectory', dirPath),

  exists: (filePath: string) =>
    ipcRenderer.invoke('file:exists', filePath),

  mkdir: (dirPath: string) =>
    ipcRenderer.invoke('file:mkdir', dirPath),

  getPlatform: () => process.platform,

  getVersion: () => '1.0.0',

  onMenuAction: (callback: (action: string) => void) => {
    ipcRenderer.on('menu:action', (_event, action) => callback(action))
  },

  removeMenuActionListener: () => {
    ipcRenderer.removeAllListeners('menu:action')
  },
} satisfies ElectronAPI)
