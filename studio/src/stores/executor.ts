// Executor Store — Pinia store for test executor session management.
// 执行器存储 — 管理用例执行器会话、配置和子进程通信的 Pinia store。

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { ExecutorSession, ExecutorSettings, ExecutorCliParams } from '../types/executor'
import { DEFAULT_CLI_PARAMS, DEFAULT_EXECUTOR_SETTINGS } from '../types/executor'
import type { LogEntry } from '../types/agent'
import { spawnExecutor, killExecutor, checkExecutorRunning, listenToExecutorEvents } from '../utils/executor-bridge'
import { resolvePythonCommand } from '../utils/resolve-python'
import { loadSettingsFile, saveSettingsFile } from '../utils/settings-store'
import { useAgentStore } from './agent'
import { readFile, writeFile, listDirectoryAll } from '../utils/desktop-bridge'
import yaml from 'js-yaml'
import YAML from 'yaml'
import { fixStaleRunningStatus, STALE_STATUS_ERROR_MSG } from '../utils/process-liveness'

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

  // 每个运行中会话的健康检查 interval / Health check interval per running session
  const _healthChecks = new Map<string, ReturnType<typeof setInterval>>()

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
    // 1. 先终止子进程，确保进程已 kill 再从 UI 移除 / Kill subprocess first; remove from UI after
    if (_listeners.has(sessionId)) {
      try { await killExecutor(sessionId); } catch { /* process may already be dead */ }
      _listeners.get(sessionId)?.()
      _listeners.delete(sessionId)
      // 同步清理健康检查 / Clean up health check too
      const hc = _healthChecks.get(sessionId)
      if (hc) { clearInterval(hc); _healthChecks.delete(sessionId) }
    }

    // 2. 确认子进程已终止，从 UI 移除 / Confirm process is dead, then remove from UI
    sessions.value = sessions.value.filter((s) => s.id !== sessionId)
    if (activeSessionId.value === sessionId) {
      activeSessionId.value = sessions.value[0]?.id ?? null
    }
    await saveSessions()
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
   * 使用 js-yaml 解析，返回原始 YAML 结构（不再 flatten 为 _app_ 前缀格式）。
   * Uses js-yaml for parsing; returns raw YAML structure (no longer flattens with _app_ prefix).
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
      return (parsed as Record<string, unknown>) ?? {}
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
   * 将 env-only 参数写入 YAML env 文件（保留注释）。
   * Write env-only parameters to YAML env file (comments preserved).
   *
   * 使用 yaml Document API 原地修改，仅更新变更的键，保留原始注释和格式。
   * Uses yaml Document API for in-place modification; only changed keys are touched,
   * preserving original comments and formatting.
   */
  async function writeEnvFile(envSuffix: string, data: Record<string, unknown>): Promise<void> {
    const rootDir = await getExecutorRootDir()
    if (!rootDir) throw new Error('Executor root directory not set')

    const envPath = envSuffix
      ? `${rootDir}/env-${envSuffix}.yml`.replace(/\\/g, '/')
      : `${rootDir}/env.yml`.replace(/\\/g, '/')

    // 解析现有 YAML（保留注释），不存在则创建空文档 / Parse existing (keep comments), or empty doc
    let doc: YAML.Document
    try {
      const content = await readFile(envPath)
      doc = YAML.parseDocument(content)
    } catch {
      doc = new YAML.Document({})
    }

    // 在 Document 上原地修改 / Modify in-place on Document
    applyEnvOverrides(doc, data)

    await writeFile(envPath, doc.toString())
  }

  /**
   * 将数据应用到 YAML Document 上，原地修改保留注释。
   * Apply data onto YAML Document in-place, preserving comments.
   *
   * _app_ 前缀的键视为嵌套对象（向后兼容），非前缀嵌套对象直接作为 YAML 映射处理，
   * null/undefined 值视为删除。
   * _app_-prefixed keys are treated as nested objects (backward compat),
   * non-prefixed nested objects are treated as YAML maps directly,
   * null/undefined values trigger deletion.
   */
  // 保存 env-only 参数时始终保留的键（防止误删执行器基础配置，如 caseFilePath/lang）。
  // Keys always preserved when saving env-only params (prevents accidentally dropping
  // executor base config such as caseFilePath/lang).
  const ENV_PRESERVE_KEYS = new Set([
    'envName', 'caseFilePath', 'scriptType', 'maxThread', 'reportName', 'apiMode', 'lang', 'excel_font',
  ])

  function applyEnvOverrides(doc: YAML.Document, data: Record<string, unknown>): void {
    // 第一步：删除文档中存在但 data 中不存在的 key（处理字段删除，保留注释）
    // Step 1: Remove keys in doc that are NOT in data (handle field deletion, preserves comments)
    if (doc.contents && YAML.isMap(doc.contents)) {
      const dataKeys = new Set(Object.keys(data))
      // 收集需要删除的 key（同时也处理 _app_ 前缀的嵌套对象 key）
      // Collect keys to delete (also handles _app_-prefixed nested object keys)
      const keysToDelete: string[] = []
      for (const item of doc.contents.items) {
        const docKey = String((item.key as YAML.Scalar).value)
        // 保留基础配置键：env-only 保存不应清掉执行器 CLI/默认配置。
        // Preserve base config keys: env-only saves must not strip executor CLI/defaults.
        if (ENV_PRESERVE_KEYS.has(docKey)) continue
        if (!dataKeys.has(docKey)) {
          // 检查是否有对应的 _app_ 前缀 key 在 data 中 / Check if corresponding _app_-prefixed key is in data
          if (!dataKeys.has(`_app_${docKey}`)) {
            keysToDelete.push(docKey)
          }
        }
      }
      for (const key of keysToDelete) {
        doc.delete(key)
      }
    }

    // 第二步：设置/更新 data 中的每个 key（处理新增和修改，保留注释）
    // Step 2: Set/update each key in data (handle add and modify, preserves comments)
    for (const [key, val] of Object.entries(data)) {
      if (key.startsWith('_app_')) {
        // _app_<name> 是嵌套对象（向后兼容）/ _app_<name> is a nested object (backward compat)
        const appName = key.slice(5)
        if (val && typeof val === 'object' && !Array.isArray(val)) {
          const obj = val as Record<string, unknown>
          const appNode = doc.getIn([appName], true)
          if (appNode && YAML.isMap(appNode)) {
            // 先删除 appNode 中存在但 obj 中不存在的子键（处理嵌套字段删除，保留注释）
            // Delete sub-keys in appNode that are NOT in obj (handle nested field deletion, preserves comments)
            const newSubKeys = new Set(Object.keys(obj))
            const subKeysToDelete: string[] = []
            for (const subItem of appNode.items) {
              const subDocKey = String((subItem.key as YAML.Scalar).value)
              if (!newSubKeys.has(subDocKey)) {
                subKeysToDelete.push(subDocKey)
              }
            }
            for (const key of subKeysToDelete) {
              appNode.delete(key)
            }
            // 然后在现有映射节点上原地更新/新增子键 / Then update/add sub-keys in-place on existing map node
            for (const [subKey, subVal] of Object.entries(obj)) {
              appNode.set(subKey, subVal)
            }
          } else {
            // 节点不存在或不是映射，整体设置 / Node missing or not a map, set as a whole
            doc.setIn([appName], obj)
          }
        }
        // _app_ 键的删除：如果 val 为 null/undefined，删除对应嵌套对象 / Delete _app_ key: remove nested object if null/undefined
        if (val === undefined || val === null) {
          doc.delete(appName)
        }
      } else if (val === undefined || val === null) {
        // null/undefined → 删除键 / delete key
        doc.delete(key)
      } else if (typeof val === 'object' && val !== null && !Array.isArray(val)) {
        // 非前缀嵌套对象 → 作为 YAML 映射处理 / Non-prefixed nested object → treat as YAML map
        const obj = val as Record<string, unknown>
        const existingNode = doc.getIn([key], true)
        if (existingNode && YAML.isMap(existingNode)) {
          // 先删除 existingNode 中存在但 obj 中不存在的子键（处理嵌套字段删除，保留注释）
          // Delete sub-keys in existingNode that are NOT in obj (handle nested field deletion, preserves comments)
          const newSubKeys = new Set(Object.keys(obj))
          const subKeysToDelete: string[] = []
          for (const subItem of existingNode.items) {
            const subDocKey = String((subItem.key as YAML.Scalar).value)
            if (!newSubKeys.has(subDocKey)) {
              subKeysToDelete.push(subDocKey)
            }
          }
          for (const key of subKeysToDelete) {
            existingNode.delete(key)
          }
          // 然后在现有映射节点上原地更新/新增子键 / Then update/add sub-keys in-place on existing map node
          for (const [subKey, subVal] of Object.entries(obj)) {
            existingNode.set(subKey, subVal)
          }
        } else {
          doc.set(key, obj)
        }
      } else {
        // 标量或数组：直接设置 / Scalar or array: set directly
        doc.set(key, val)
      }
    }
  }

  // ---- Subprocess lifecycle / 子进程生命周期 ----

  // 参数定义来自 shared/schemas/cli/executor.json（与 Python main.py parser 同步）
  // Arg definitions from shared/schemas/cli/executor.json (synced with Python main.py parser)
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

    // 注册事件监听（先 await 监听器就绪，再 spawn 进程，防止事件丢失）
    // Register event listener (await listener readiness before spawn to prevent event loss)
    const unlisten = await listenToExecutorEvents(sessionId, (line, level) => {
      appendLog(sessionId, level, line)
      // 尝试解析 JSON 完成行 / Try parsing JSON completion line
      tryParseCompletion(sessionId, line)
    })
    _listeners.set(sessionId, unlisten)

    // 启动子进程 / Spawn subprocess
    try {
      // Python 路径优先使用 agent config（共享设置）/ Use agent config python path
      const agentStore = useAgentStore()
      if (!agentStore.configLoaded) {
        await agentStore.loadConfig()
      }
      const cmd = resolvePythonCommand(agentStore.config)
      // 打印即将执行的完整命令，便于定位问题 / Log the full command for debugging
      const fullCmd = [cmd.exe, ...cmd.preArgs, ...args].join(' ')
      appendLog(sessionId, 'info', `[CMD] ${fullCmd}`)
      await spawnExecutor(
        sessionId,
        agentStore.config.executorRootDir,
        cmd.exe,
        cmd.preArgs,
        args,
      )
      appendLog(sessionId, 'info', 'Executor process started')
      _startHealthCheck(sessionId)
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

  /**
   * 启动进程健康检查 — 每 5 秒检查子进程是否存活。
   * Start process health check — poll every 5s to see if subprocess is still alive.
   */
  function _startHealthCheck(sessionId: string): void {
    const interval = setInterval(async () => {
      const s = sessions.value.find(x => x.id === sessionId)
      if (!s || s.status !== 'running') {
        clearInterval(interval)
        _healthChecks.delete(sessionId)
        return
      }
      try {
        const alive = await checkExecutorRunning(sessionId)
        if (!alive) {
          s.status = 'error'
          s.error = 'Process exited unexpectedly'
          appendLog(sessionId, 'error', 'Process exited unexpectedly — 进程可能已崩溃 / may have crashed')
          _listeners.get(sessionId)?.()
          _listeners.delete(sessionId)
          clearInterval(interval)
          _healthChecks.delete(sessionId)
          await saveSessions()
        }
      } catch { /* 忽略检查错误 / ignore check errors */ }
    }, 5000)
    _healthChecks.set(sessionId, interval)
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
    // 清理健康检查 / Clean up health check
    const hc = _healthChecks.get(sessionId)
    if (hc) {
      clearInterval(hc)
      _healthChecks.delete(sessionId)
    }
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
        const hc = _healthChecks.get(sessionId)
        if (hc) { clearInterval(hc); _healthChecks.delete(sessionId) }
        saveSessions()
      }
    } catch {
      // 不是 JSON 行，继续 / Not a JSON line, continue
    }
  }

  // ---- Init / 初始化 ----

  async function initialize(): Promise<void> {
    // 幂等保护：已初始化则跳过 / Idempotent guard: skip if already initialized
    if (settingsLoaded.value) return
    await loadSettings()
    await loadSessions()
    // 修复启动时卡在 running 状态的旧会话 / Fix stale running sessions on startup
    if (await fixStaleRunningStatus(
      sessions.value,
      checkExecutorRunning,
      ['running'],
      STALE_STATUS_ERROR_MSG,
    )) {
      // 为被修复的项添加日志 / Add log for fixed items
      for (const s of sessions.value) {
        if (s.error === STALE_STATUS_ERROR_MSG) {
          appendLog(s.id, 'error', '会话状态已修正：进程已丢失（Studio 关闭或崩溃）/ Session status corrected: process lost (Studio was closed or crashed)')
        }
      }
      await saveSessions()
    }
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
