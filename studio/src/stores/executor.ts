// Executor Store — Pinia store for test executor session management.
// 执行器存储 — 管理用例执行器会话、配置和子进程通信的 Pinia store。

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { ExecutorSession, ExecutorSettings, ExecutorCliParams } from '../types/executor'
import { DEFAULT_CLI_PARAMS, DEFAULT_EXECUTOR_SETTINGS } from '../types/executor'
import type { LogEntry } from '../types/agent'
import { spawnExecutor, killExecutor, listenToExecutorEvents } from '../utils/executor-bridge'
import { loadSettingsFile, saveSettingsFile } from '../utils/settings-store'
import { readFile, writeFile, exists } from '../utils/desktop-bridge'

const SESSIONS_FILE = 'executor_sessions.json'
const SETTINGS_FILE = 'executor_config.json'

// ============================================================================
// Store / 存储
// ============================================================================

export const useExecutorStore = defineStore('executor', () => {
  // ---- State / 状态 ----

  const sessions = ref<ExecutorSession[]>([])
  const activeSessionId = ref<string | null>(null)
  const settings = ref<ExecutorSettings>({ ...DEFAULT_EXECUTOR_SETTINGS })
  const settingsLoaded = ref(false)

  // 编辑器联动：每个编辑器路径对应的 CLI 参数 / Editor integration: CLI params per editor path
  const editorCliParams = ref<Record<string, ExecutorCliParams>>({})

  // 每个运行中会话的 listener 清理函数 / Listener cleanup per running session
  const _listeners = new Map<string, () => void>()

  // ---- Getters / 计算属性 ----

  const activeSession = computed(() =>
    sessions.value.find((s) => s.id === activeSessionId.value) ?? null,
  )

  const sortedSessions = computed(() =>
    [...sessions.value].sort((a, b) => b.updatedAt - a.updatedAt),
  )

  // ---- Settings / 设置 ----

  async function loadSettings(): Promise<void> {
    settings.value = await loadSettingsFile(SETTINGS_FILE, DEFAULT_EXECUTOR_SETTINGS)
    settingsLoaded.value = true
  }

  async function saveSettings(): Promise<void> {
    await saveSettingsFile(SETTINGS_FILE, settings.value)
  }

  // ---- Sessions / 会话管理 ----

  async function loadSessions(): Promise<void> {
    const saved = await loadSettingsFile<ExecutorSession[]>(SESSIONS_FILE, [])
    sessions.value = saved
  }

  async function saveSessions(): Promise<void> {
    await saveSettingsFile(SESSIONS_FILE, sessions.value)
  }

  function createSession(params: {
    envSuffix: string
    caseFilePath: string
    yamlDir: string
    yamlFiles: string
    envOnlyParams: Record<string, unknown>
    cliParams: ExecutorCliParams
  }): string {
    const id = `exec_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
    const name = params.envSuffix
      ? `${params.envSuffix}`
      : 'default'

    const session: ExecutorSession = {
      id,
      name,
      status: 'pending',
      createdAt: Date.now(),
      updatedAt: Date.now(),
      envSuffix: params.envSuffix,
      caseFilePath: params.caseFilePath,
      yamlDir: params.yamlDir,
      yamlFiles: params.yamlFiles,
      envOnlyParams: params.envOnlyParams,
      cliParams: params.cliParams,
      logLines: [],
    }

    sessions.value.unshift(session)
    activeSessionId.value = id
    saveSessions()
    return id
  }

  function selectSession(sessionId: string | null): void {
    activeSessionId.value = sessionId
  }

  async function removeSession(sessionId: string): Promise<void> {
    // 1. 先从 UI 中移除（同步，立即生效）/ Remove from UI first (sync, immediate)
    sessions.value = sessions.value.filter((s) => s.id !== sessionId)
    if (activeSessionId.value === sessionId) {
      activeSessionId.value = sessions.value[0]?.id ?? null
    }

    // 2. 再异步清理子进程和持久化（后台进行，不阻塞 UI）/ Then cleanup async (background)
    if (_listeners.has(sessionId)) {
      killExecutor(sessionId).catch(() => {})
      _listeners.get(sessionId)?.()
      _listeners.delete(sessionId)
    }
    saveSessions().catch(() => {})
  }

  // ---- 从 env 文件读取 / Read from env file ----

  async function readEnvSuffixes(): Promise<string[]> {
    // 扫描执行器根目录下的 env-*.yml 文件 / Scan env-*.yml files in executor root
    const suffixes: string[] = ['']
    try {
      const rootDir = settings.value.executorRootDir
      if (!rootDir) return suffixes
      // 简单尝试读取常见后缀 / Try reading common suffixes
      const commonSuffixes = ['local', 'dev', 'prod', 'test', 'staging']
      for (const suffix of commonSuffixes) {
        const envPath = `${rootDir}/env-${suffix}.yml`.replace(/\\/g, '/')
        try {
          const envExists = await exists(envPath)
          if (envExists) suffixes.push(suffix)
        } catch { /* skip */ }
      }
    } catch { /* browser mode */ }
    return suffixes
  }

  async function readEnvFile(envSuffix: string): Promise<Record<string, unknown>> {
    try {
      const rootDir = settings.value.executorRootDir
      if (!rootDir) return {}
      const envPath = envSuffix
        ? `${rootDir}/env-${envSuffix}.yml`.replace(/\\/g, '/')
        : `${rootDir}/env.yml`.replace(/\\/g, '/')
      const content = await readFile(envPath)
      // 简单 YAML 解析（仅提取顶层标量 + apps 的 baseURL 等）
      // Simple YAML parsing — extract top-level scalars and app configs
      const result: Record<string, unknown> = {}
      let currentApp: string | null = null
      for (const line of content.split('\n')) {
        const trimmed = line.trim()
        if (!trimmed || trimmed.startsWith('#')) continue
        // 检测 App 块 / Detect app block
        const appMatch = trimmed.match(/^(\w+):\s*$/)
        if (appMatch && !['processor_configs'].includes(appMatch[1]) && !line.startsWith(' ')) {
          currentApp = appMatch[1]
          result[`_app_${currentApp}`] = {}
          continue
        }
        // 检测简单键值对 / Detect key-value pairs
        const kvMatch = trimmed.match(/^(\w+):\s*(.+)$/)
        if (kvMatch) {
          const key = kvMatch[1]
          const val = kvMatch[2].trim().replace(/^['"]|['"]$/g, '')
          if (currentApp) {
            const appObj = result[`_app_${currentApp}`] as Record<string, unknown>
            appObj[key] = val
          } else {
            result[key] = val
          }
        }
      }
      return result
    } catch {
      return {}
    }
  }

  async function writeEnvFile(envSuffix: string, data: Record<string, unknown>): Promise<void> {
    // 写入 env-only 参数到 env 文件 / Write env-only params to env file
    try {
      const rootDir = settings.value.executorRootDir
      if (!rootDir) return
      const envPath = envSuffix
        ? `${rootDir}/env-${envSuffix}.yml`.replace(/\\/g, '/')
        : `${rootDir}/env.yml`.replace(/\\/g, '/')
      // 读取原始文件内容，替换对应行 / Read original content, replace matching lines
      const original = await readFile(envPath)
      const lines = original.split('\n')
      const result: string[] = []
      let currentApp: string | null = null
      for (const line of lines) {
        const trimmed = line.trim()
        const appMatch = trimmed.match(/^(\w+):\s*$/)
        if (appMatch && !line.startsWith(' ') && data[`_app_${appMatch[1]}`]) {
          currentApp = appMatch[1]
          result.push(line)
          continue
        }
        if (currentApp && trimmed === '') {
          currentApp = null
        }
        const kvMatch = trimmed.match(/^(\w+):\s*(.+)$/)
        if (kvMatch) {
          const key = kvMatch[1]
          if (currentApp) {
            const appData = data[`_app_${currentApp}`] as Record<string, unknown> | undefined
            if (appData && key in appData) {
              result.push(`  ${key}: ${appData[key]}`)
              continue
            }
          } else if (key in data) {
            result.push(`${key}: ${data[key]}`)
            continue
          }
        }
        result.push(line)
      }
      await writeFile(envPath, result.join('\n'))
    } catch {
      // 静默失败 / Silently fail
    }
  }

  // ---- Subprocess lifecycle / 子进程生命周期 ----

  function buildCliArgs(session: ExecutorSession): string[] {
    const args: string[] = ['main.py']
    const cp = session.cliParams

    if (cp.scriptType) args.push('--scriptType', cp.scriptType)
    if (session.envSuffix) args.push('--envName', session.envSuffix)
    if (session.caseFilePath) args.push('--caseFilePath', session.caseFilePath)
    if (cp.maxThread && cp.maxThread > 0) args.push('--maxThread', String(cp.maxThread))
    if (cp.reportName) args.push('--reportName', cp.reportName)
    if (cp.apiMode) args.push('--apiMode', cp.apiMode)
    if (session.yamlDir) args.push('--yamlDir', session.yamlDir)
    if (session.yamlFiles) args.push('--yamlFiles', session.yamlFiles)

    return args
  }

  async function startSession(sessionId: string): Promise<void> {
    const session = sessions.value.find((s) => s.id === sessionId)
    if (!session) return

    session.status = 'running'
    session.logLines = []
    session.reportPath = undefined
    session.summary = undefined
    session.error = undefined
    session.updatedAt = Date.now()

    // 如果需要同步，写入 CLI 参数到 env 文件 / If sync enabled, write CLI params to env
    // (同步开关在 agent store 的 config.saveToEnvFile 中 / toggle in agent store config)
    // 注意：这里需要引入 agent store 来检查 / Need to import agent store to check
    // 为了解耦，executor store 有自己的独立同步设置 / Decoupled: executor has its own logic

    const args = buildCliArgs(session)

    // 注册事件监听 / Register event listener
    const unlisten = listenToExecutorEvents(sessionId, (line, level) => {
      appendLog(sessionId, level, line)
      // 尝试解析 JSON 完成行 / Try parsing JSON completion line
      tryParseCompletion(sessionId, line)
    })
    _listeners.set(sessionId, unlisten)

    // 启动子进程 / Spawn subprocess
    try {
      // Python 路径优先使用 agent config（共享设置）/ Use agent config python path
      const { useAgentStore } = await import('./agent')
      const agentStore = useAgentStore()
      const pythonExe = agentStore.config.pythonExePath || 'python'
      await spawnExecutor(
        sessionId,
        settings.value.executorRootDir,
        pythonExe,
        args,
      )
      appendLog(sessionId, 'info', 'Executor process started')
    } catch (e: unknown) {
      const err = e as Error
      session.status = 'error'
      session.error = err?.message || String(e)
      appendLog(sessionId, 'error', `Failed to start: ${session.error}`)
      _listeners.get(sessionId)?.()
      _listeners.delete(sessionId)
    }

    await saveSessions()
  }

  async function terminateSession(sessionId: string): Promise<void> {
    const session = sessions.value.find((s) => s.id === sessionId)
    if (!session) return
    session.status = 'error'
    session.error = 'Terminated by user'
    session.updatedAt = Date.now()
    appendLog(sessionId, 'info', 'Session terminated by user')

    try {
      await killExecutor(sessionId)
    } catch { /* process may already be dead */ }

    _listeners.get(sessionId)?.()
    _listeners.delete(sessionId)
    await saveSessions()
  }

  // ---- Logger / 日志 ----

  function appendLog(sessionId: string, level: LogEntry['level'], message: string): void {
    const session = sessions.value.find((s) => s.id === sessionId)
    if (!session) return
    session.logLines.push({
      ts: new Date().toLocaleTimeString(),
      level,
      message,
    })
  }

  // ---- Completion parser / 完成行解析 ----

  function tryParseCompletion(sessionId: string, line: string): void {
    const session = sessions.value.find((s) => s.id === sessionId)
    if (!session || session.status !== 'running') return

    try {
      const parsed = JSON.parse(line.trim())
      if (parsed && typeof parsed.output === 'string') {
        session.status = 'completed'
        session.reportPath = parsed.output
        session.summary = {
          single_cases: parsed.single_cases ?? 0,
          biz_flows: parsed.biz_flows ?? 0,
          single_passed: parsed.single_passed ?? 0,
          biz_passed: parsed.biz_passed ?? 0,
        }
        session.updatedAt = Date.now()
        _listeners.get(sessionId)?.()
        _listeners.delete(sessionId)
        saveSessions()
      }
    } catch {
      // 不是 JSON 行，继续 / Not a JSON line, continue
    }
  }

  // ---- Init / 初始化 ----

  async function initialize(): Promise<void> {
    await loadSettings()
    await loadSessions()
  }

  // ---- Editor integration / 编辑器联动 ----

  function getEditorCliParams(editorPath: string): ExecutorCliParams {
    return editorCliParams.value[editorPath] ?? { ...DEFAULT_CLI_PARAMS }
  }

  function setEditorCliParams(editorPath: string, params: ExecutorCliParams): void {
    editorCliParams.value[editorPath] = { ...params }
  }

  return {
    // State
    sessions,
    activeSessionId,
    settings,
    settingsLoaded,
    editorCliParams,
    // Getters
    activeSession,
    sortedSessions,
    // Actions
    loadSettings,
    saveSettings,
    loadSessions,
    saveSessions,
    createSession,
    selectSession,
    removeSession,
    readEnvSuffixes,
    readEnvFile,
    writeEnvFile,
    startSession,
    terminateSession,
    initialize,
    getEditorCliParams,
    setEditorCliParams,
  }
})
