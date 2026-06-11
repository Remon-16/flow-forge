import type { ElectronAPI } from '../../electron/preload'

const isElectron = typeof window !== 'undefined' && !!(window as any).electronAPI

function getAPI(): ElectronAPI | null {
  if (!isElectron) return null
  return (window as any).electronAPI as ElectronAPI
}

export async function openFileDialog(
  filters?: { name: string; extensions: string[] }[],
): Promise<string | null> {
  const api = getAPI()
  if (api) return api.openFileDialog({ filters })

  // Browser fallback: use hidden file input
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
        // Store file data in a temp path (won't persist, but consistent API)
        ;(input as any)._result = { name: file.name, data: reader.result }
        resolve(file.name) // Return file name; handling is done in the caller
      }
      ;(reader as FileReader).readAsArrayBuffer(file)
    }
    input.oncancel = () => resolve(null)
    input.click()
  })
}

export async function openDirectoryDialog(): Promise<string | null> {
  const api = getAPI()
  if (api) return api.openDirectoryDialog()
  throw new Error('Directory selection is not supported in browser mode. Please use the desktop app.')
}

export async function readFile(filePath: string, encoding: string = 'utf-8'): Promise<string> {
  const api = getAPI()
  if (api) return api.readFile(filePath, encoding)
  throw new Error('Direct file reading is not supported in browser mode. Please use "Open File" instead.')
}

export async function readFileBuffer(filePath: string): Promise<ArrayBuffer> {
  const api = getAPI()
  if (api) return api.readFileBuffer(filePath)
  throw new Error('Direct file reading is not supported in browser mode.')
}

export async function writeFile(filePath: string, content: string): Promise<void> {
  const api = getAPI()
  if (api) return api.writeFile(filePath, content)
  throw new Error('Direct file writing is not supported in browser mode. Please use "Save As" instead.')
}

export async function writeFileBuffer(filePath: string, buffer: ArrayBuffer): Promise<void> {
  const api = getAPI()
  if (api) return api.writeFileBuffer(filePath, buffer)
  throw new Error('Direct file writing is not supported in browser mode.')
}

export async function readDirectory(dirPath: string): Promise<ElectronAPI['readDirectory'] extends (...args: any[]) => any ? ReturnType<ElectronAPI['readDirectory']> : never> {
  const api = getAPI()
  if (api) return api.readDirectory(dirPath) as any
  throw new Error('Directory reading is not supported in browser mode.')
}

export async function exists(filePath: string): Promise<boolean> {
  const api = getAPI()
  if (api) return api.exists(filePath)
  return false
}

export async function mkdir(dirPath: string): Promise<void> {
  const api = getAPI()
  if (api) return api.mkdir(dirPath)
}

export function getPlatform(): string {
  const api = getAPI()
  if (api) return api.getPlatform()
  return 'browser'
}

export { isElectron }

export type { ElectronAPI }
