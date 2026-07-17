// Executor Store — Pinia store for test executor session management.
// 执行器存储 — 管理用例执行器会话、配置和子进程通信的 Pinia store。

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { ExecutorSession, ExecutorSettings, ExecutorCliParams } from '../types/executor'
import { DEFAULT_CLI_PARAMS, DEFAULT_EXECUTOR_SETTINGS } from '../types/executor'
import type { LogEntry } from '../types/agent'
import { spawnExecutor, killExecutor, listenToExecutorEvents } from '../utils/executor-bridge'
import { resolvePythonExe } from '../utils/resolve-python'
import { loadSettingsFile, saveSettingsFile } from '../utils/settings-store'
import { readFile, writeFile, exists, listDirectoryAll } from '../utils/desktop-bridge'
import yaml from 'js-yaml'

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

  /**
   * 获取执行器根目录（从 AgentConfig 共享配置读取）。
   * Get executor root directory from shared AgentConfig.
   *
   * AgentSettings.vue 将 executorRootDir 写入 agent.config，
   * executor 自身的 settings.executorRootDir 无 UI 写入入口。
   * 如果 agent config 尚未从磁盘加载，则先懒加载。
   * AgentSettings.vue writes executorRootDir to agent.config;
   * the executor's own settings.executorRootDir is never written by any UI.
   * Lazily loads agent config from disk if not already loaded.
   */
  async function getExecutorRootDir(): Promise<string> {
    try {
      const { useAgentStore } = await import('./agent')
      const agentStore = useAgentStore()
      if (!agentStore.configLoaded) {
        await agentStore.loadConfig()
      }
      return agentStore.config.executorRootDir
    } catch (e) {
      console.error('[executor] getExecutorRootDir failed:', e)
      return ''
    }
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

  /**
   * 扫描执行器根目录下的 env-*.yml 文件，返回后缀列表。
   * Scan executor root for env-*.yml files, return suffix list.
   * 默认包含空后缀（env.yml），额外后缀通过目录扫描获得。
   * Default includes empty suffix (env.yml); additional suffixes from directory scan.
   */
  async function readEnvSuffixes(): Promise<string[]> {
    const suffixes: string[] = ['']
    try {
      const rootDir = await getExecutorRootDir()
      if (!rootDir) return suffixes
      const entries = await listDirectoryAll(rootDir)
      for (const entry of entries) {
        if (entry.isDirectory) continue
        const match = entry.name.match(/^env-(.+)\.yml$/)
        if (match) suffixes.push(match[1])
      }
    } catch (e) {
      console.error('[executor] readEnvSuffixes failed:', e)
    }
    return suffixes
  }

  /**
   * 从 YAML env 文件解析参数。
   * Parse parameters from YAML env file.
   *
   * 使用 js-yaml 解析，结果扁平化为 _app_ 前缀格式与 ExecutorForm 兼容。
   * Uses js-yaml for parsing; flattens nested app blocks with _app_ prefix
   * for compatibility with ExecutorForm's loadEnvData().
   */
  async function readEnvFile(envSuffix: string): Promise<Record<string, unknown>> {
    const rootDir = await getExecutorRootDir()
    if (!rootDir) return {}
    const envPath = envSuffix
      ? `${rootDir}/env-${envSuffix}.yml`.replace(/\\/g, '/')
      : `${rootDir}/env.yml`.replace(/\\/g, '/')
    try {
      const content = await readFile(envPath)
      const parsed = yaml.load(content)
      return flattenEnvConfig(parsed)
    } catch (e: unknown) {
      const err = e as Error
      const msg = err?.message || String(e)
      // 文件不存在为预期情况（未创建 env 文件），静默返回空 / File not found is expected (no env file yet); silent
      if (msg.includes('os error 2') || msg.includes('No such file') || msg.includes('not found') || msg.includes('NotFound')) {
        console.info('[executor] env file not found (ok):', envPath)
        return {}
      }
      // 其他错误（权限、YAML 格式错误等）抛出给调用方处理 / Other errors (perms, bad YAML) throw to caller
      console.error('[executor] readEnvFile failed:', e)
      throw e
    }
  }

  /**
   * 将 js-yaml 解析结果扁平化：嵌套对象用 _app_ 前缀标记。
   * Flatten js-yaml parse result: nested objects prefixed with _app_.
   */
  function flattenEnvConfig(parsed: unknown): Record<string, unknown> {
    const result: Record<string, unknown> = {}
    if (parsed === null || parsed === undefined) return result
    if (typeof parsed !== 'object') return result
    if (Array.isArray(parsed)) return result

    const obj = parsed as Record<string, unknown>
    for (const [key, val] of Object.entries(obj)) {
      if (typeof val === 'object' && val !== null && !Array.isArray(val)) {
        // 嵌套对象 → _app_ 前缀 / Nested object → _app_ prefix
        result[`_app_${key}`] = val
      } else {
        // 顶层标量或数组 → 保持原样 / Top-level scalar or array → as-is
        result[key] = val
      }
    }
    return result
  }

  /**
   * 将 env-only 参数写入 YAML env 文件。
   * Write env-only parameters to YAML env file.
   *
   * 读取现有 YAML → 扁平化 → 合并新数据 → 还原嵌套 → js-yaml 写入。
   * 支持新增键（不只是替换已有行），文件不存在时自动创建。
   * Read existing YAML → flatten → merge incoming → unflatten → write via js-yaml.
   * Supports adding new keys (not just replacing existing lines);
   * auto-creates file if missing. Errors propagate to callers (no silent swallow).
   */
  async function writeEnvFile(envSuffix: string, data: Record<string, unknown>): Promise<void> {
    const rootDir = await getExecutorRootDir()
    if (!rootDir) throw new Error('Executor root directory not set')

    const envPath = envSuffix
      ? `${rootDir}/env-${envSuffix}.yml`.replace(/\\/g, '/')
      : `${rootDir}/env.yml`.replace(/\\/g, '/')

    // 读取现有 YAML（不存在则用空对象）/ Read existing YAML (empty if missing)
    let existing: Record<string, unknown> = {}
    try {
      const content = await readFile(envPath)
      const parsed = yaml.load(content)
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        existing = parsed as Record<string, unknown>
      }
    } catch {
      // 文件不存在或无法解析，从头创建 / File missing or unparseable, start fresh
    }

    // 扁平化 → 合并 → 还原嵌套 → 写入 / Flatten → merge → unflatten → write
    const flatExisting = flattenEnvConfig(existing)
    const merged = { ...flatExisting, ...data }
    const nested = unflattenEnvConfig(merged)
    const yamlStr = yaml.dump(nested, { lineWidth: -1, noRefs: true })
    await writeFile(envPath, yamlStr)
  }

  /**
   * 将扁平化数据还原为嵌套 YAML 结构。
   * Restore flattened _app_ prefixed data to nested YAML-compatible structure.
   */
  function unflattenEnvConfig(data: Record<string, unknown>): Record<string, unknown> {
    const result: Record<string, unknown> = {}
    const apps: Record<string, unknown> = {}

    for (const [key, val] of Object.entries(data)) {
      if (key.startsWith('_app_')) {
        const appName = key.slice(5) // remove _app_ prefix / 去掉 _app_ 前缀
        apps[appName] = val
      } else {
        result[key] = val
      }
    }

    // 将 app 块合并回顶层 / Merge app blocks back to top level
    Object.assign(result, apps)
    return result
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
      const pythonExe = resolvePythonExe(agentStore.config)
      await spawnExecutor(
        sessionId,
        agentStore.config.executorRootDir,
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
