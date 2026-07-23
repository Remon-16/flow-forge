// Counter Store — Pinia store for diagnostic counter session management.
// 计数器存储 — 管理诊断计数器会话、配置和子进程通信的 Pinia store。
// 完全对应 stores/executor.ts 的核心结构 / Mirrors executor.ts core structure.

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { CounterSession } from '../types/counter'
import type { LogEntry } from '../types/agent'
import { spawnCounter, killCounter, checkCounterRunning, listenToCounterEvents } from '../utils/counter-bridge'
import { resolvePythonCommand } from '../utils/resolve-python'
import { loadSettingsFile, saveSettingsFile } from '../utils/settings-store'
import { useAgentStore } from './agent'
import { fixStaleRunningStatus, STALE_STATUS_ERROR_MSG } from '../utils/process-liveness'

const SESSIONS_FILE = 'counter_sessions.json'
const SETTINGS_FILE = 'counter_config.json'

// ============================================================================
// 设置类型 / Settings type
// ============================================================================

interface CounterSettings {
  /** python/ 目录路径（counter_main.py 所在）/ python/ directory path (where counter_main.py lives) */
  pythonWorkingDir: string
}

const DEFAULT_SETTINGS: CounterSettings = {
  pythonWorkingDir: '',
}

// ============================================================================
// Store / 存储
// ============================================================================

export const useCounterStore = defineStore('counter', () => {
  // ---- State / 状态 ----

  const sessions = ref<CounterSession[]>([])
  const activeSessionId = ref<string | null>(null)
  const settings = ref<CounterSettings>({ ...DEFAULT_SETTINGS })
  const settingsLoaded = ref(false)

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
    settings.value = await loadSettingsFile(SETTINGS_FILE, DEFAULT_SETTINGS)
    settingsLoaded.value = true
  }

  async function saveSettings(): Promise<void> {
    await saveSettingsFile(SETTINGS_FILE, settings.value)
  }

  /**
   * 获取 python/ 工作目录 — 优先使用已配置路径，否则复用 executorRootDir。
   * Get python/ working directory — use configured path, or reuse executorRootDir.
   *
   * counter_main.py 与 main.py 同在 python/ 目录下，直接复用 executorRootDir 即可，
   * 无需从 agentRootDir 推导。Python 环境（conda/venv/system）由 resolvePythonCommand() 处理。
   * counter_main.py is alongside main.py in python/; just reuse executorRootDir.
   * Python environment (conda/venv/system) is handled by resolvePythonCommand().
   */
  async function getPythonWorkingDir(): Promise<string> {
    if (settings.value.pythonWorkingDir) {
      return settings.value.pythonWorkingDir
    }
    try {
      const agentStore = useAgentStore()
      if (!agentStore.configLoaded) {
        await agentStore.loadConfig()
      }
      // 直接复用 executorRootDir（用户已在 AgentSettings 中正确配置）
      // Reuse executorRootDir (already configured by user in AgentSettings)
      const dir = agentStore.config.executorRootDir
      if (dir) {
        return dir.replace(/\\/g, '/')
      }
    } catch (e) {
      console.error('[counter] getPythonWorkingDir failed:', e)
    }
    return ''
  }

  // ---- Sessions / 会话管理 ----

  async function loadSessions(): Promise<void> {
    const saved = await loadSettingsFile<CounterSession[]>(SESSIONS_FILE, [])
    sessions.value = saved
  }

  async function saveSessions(): Promise<void> {
    await saveSettingsFile(SESSIONS_FILE, sessions.value)
  }

  function createSession(outputDir: string): string {
    const id = `counter_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
    const name = new Date().toLocaleTimeString()

    const session: CounterSession = {
      id,
      name,
      status: 'pending',
      createdAt: Date.now(),
      updatedAt: Date.now(),
      outputDir,
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
      try { await killCounter(sessionId); } catch { /* process may already be dead */ }
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

  // ---- Subprocess lifecycle / 子进程生命周期 ----

  /**
   * 从 shared/schemas/cli/counter.json 读取 flag 定义，构建 CLI 参数。
   * Build CLI args from shared/schemas/cli/counter.json flag definitions.
   */
  function buildCliArgs(session: CounterSession): string[] {
    const args: string[] = ['counter_main.py']
    args.push('--output-dir', session.outputDir)
    return args
  }

  async function startSession(sessionId: string): Promise<void> {
    const session = sessions.value.find((s) => s.id === sessionId)
    if (!session) return

    session.status = 'running'
    session.logLines = []
    session.totalCounts = undefined
    session.error = undefined
    session.updatedAt = Date.now()

    const args = buildCliArgs(session)

    // 注册事件监听（先 await 监听器就绪，再 spawn 进程，防止事件丢失）
    // Register event listener (await listener readiness before spawn to prevent event loss)
    const unlisten = await listenToCounterEvents(sessionId, (line, level) => {
      appendLog(sessionId, level, line)
      // 尝试解析 JSON 完成行 / Try parsing JSON completion line
      tryParseCompletion(sessionId, line)
    })
    _listeners.set(sessionId, unlisten)

    // 启动子进程 / Spawn subprocess
    try {
      // Python 路径复用 agent config（共享设置）/ Use agent config python path
      const agentStore = useAgentStore()
      if (!agentStore.configLoaded) {
        await agentStore.loadConfig()
      }
      const cmd = resolvePythonCommand(agentStore.config)
      const workingDir = await getPythonWorkingDir()
      if (!workingDir) {
        throw new Error('Python working directory not configured. Please set agent root directory in Settings.')
      }
      await spawnCounter(
        sessionId,
        workingDir,
        cmd.exe,
        cmd.preArgs,
        args,
      )
      appendLog(sessionId, 'info', 'Counter process started')
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
        const alive = await checkCounterRunning(sessionId)
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
      await killCounter(sessionId)
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
      if (parsed && typeof parsed.total_counts === 'number') {
        session.status = 'completed'
        session.totalCounts = parsed.total_counts
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
      checkCounterRunning,
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

  return {
    // State
    sessions,
    activeSessionId,
    settings,
    settingsLoaded,
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
    startSession,
    terminateSession,
    initialize,
  }
})
