import { ipcMain, dialog, BrowserWindow } from 'electron'

export function registerDialogHandlers() {
  ipcMain.handle('dialog:openFile', async (_event, options?: {
    filters?: { name: string; extensions: string[] }[]
    defaultPath?: string
  }) => {
    const window = BrowserWindow.getFocusedWindow()
    const result = await dialog.showOpenDialog(window!, {
      title: '打开文件',
      properties: ['openFile'],
      filters: options?.filters || [
        { name: 'Test Case Files', extensions: ['xlsx', 'yaml', 'yml'] },
        { name: 'All Files', extensions: ['*'] },
      ],
      defaultPath: options?.defaultPath,
    })

    if (result.canceled || result.filePaths.length === 0) return null
    return result.filePaths[0]
  })

  ipcMain.handle('dialog:openDirectory', async (_event, defaultPath?: string) => {
    const window = BrowserWindow.getFocusedWindow()
    const result = await dialog.showOpenDialog(window!, {
      title: '打开目录',
      properties: ['openDirectory'],
      defaultPath,
    })

    if (result.canceled || result.filePaths.length === 0) return null
    return result.filePaths[0]
  })

  ipcMain.handle('dialog:saveFile', async (_event, options?: {
    defaultPath?: string
    filters?: { name: string; extensions: string[] }[]
  }) => {
    const window = BrowserWindow.getFocusedWindow()
    const result = await dialog.showSaveDialog(window!, {
      title: '保存文件',
      defaultPath: options?.defaultPath,
      filters: options?.filters || [
        { name: 'Test Case Files', extensions: ['xlsx', 'yaml', 'yml'] },
        { name: 'All Files', extensions: ['*'] },
      ],
    })

    if (result.canceled || !result.filePath) return null
    return result.filePath
  })
}
