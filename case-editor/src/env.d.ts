/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
}

declare module 'js-yaml' {
  export function load(input: string, opts?: any): any
  export function dump(obj: any, opts?: any): string
  export const DEFAULT_SCHEMA: any
}

interface FileEntry {
  name: string
  path: string
  isDirectory: boolean
  children?: FileEntry[]
}

interface ElectronAPI {
  openFileDialog(options?: { filters?: { name: string; extensions: string[] }[]; defaultPath?: string }): Promise<string | null>
  openDirectoryDialog(defaultPath?: string): Promise<string | null>
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

declare global {
  interface Window {
    electronAPI?: ElectronAPI
  }
}

export {}
