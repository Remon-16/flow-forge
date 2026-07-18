// Converter Store — Pinia store for format converter session management.
// 转换器存储 — 管理用例格式转换器会话和子进程通信的 Pinia store。

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { ConverterSession, ConverterDirection } from '../types/converter'
import type { LogEntry } from '../types/agent'
import { spawnConverter, killConverter, checkConverterRunning, listenToConverterEvents } from '../utils/converter-bridge'
import { resolvePythonCommand } from '../utils/resolve-python'
import { loadSettingsFile, saveSettingsFile } from '../utils/settings-store'
import { useAgentStore } from './agent'

const SESSIONS_FILE = 'converter_sessions.json'

// ============================================================================
// Store / 存储
// ============================================================================

export const useConverterStore = defineStore('converter', () => {
  // ---- State / 状态 ----

  const sessions = ref<ConverterSession[]>([])
  const activeSessionId = ref<string | null>(null)

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

  // ---- Sessions / 会话管理 ----

  async function loadSessions(): Promise<void> {
    const saved = await loadSettingsFile<ConverterSession[]>(SESSIONS_FILE, [])
    sessions.value = saved
  }

  async function saveSessions(): Promise<void> {
    await saveSettingsFile(SESSIONS_FILE, sessions.value)
  }

  function createSession(params: {
    direction: ConverterDirection
    inputPath: string
    outputPath: string
    interfacesDir: string
    singleCasesDir: string
    bizFlowsDir: string
    configDir: string
    processorsDir: string
  }): string {
    const id = `conv_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
    const name = params.direction

    const session: ConverterSession = {
      id,
      name,
      direction: params.direction,
      status: 'pending',
      createdAt: Date.now(),
      updatedAt: Date.now(),
      inputPath: params.inputPath,
      outputPath: params.outputPath,
      interfacesDir: params.interfacesDir,
      singleCasesDir: params.singleCasesDir,
      bizFlowsDir: params.bizFlowsDir,
      configDir: params.configDir,
      processorsDir: params.processorsDir,
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
      try { await killConverter(sessionId); } catch { /* process may already be dead */ }
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

  // ---- CLI args builder / CLI 参数构建 ----

  // 参数定义来自 shared/schemas/cli/converter.json（与 Python converter_main.py parser 同步）
  // Arg definitions from shared/schemas/cli/converter.json (synced with Python converter_main.py parser)
  function buildCliArgs(session: ConverterSession): string[] {
    const args: string[] = ['converter_main.py']

    switch (session.direction) {
      case 'excel2yaml':
        args.push('excel2yaml')
        if (session.inputPath) args.push('--input', session.inputPath)
        if (session.outputPath) args.push('--output', session.outputPath)
        break
      case 'yaml2excel':
        args.push('yaml2excel')
        if (session.interfacesDir) args.push('--interfaces', session.interfacesDir)
        if (session.singleCasesDir) args.push('--single-cases', session.singleCasesDir)
        if (session.bizFlowsDir) args.push('--biz-flows', session.bizFlowsDir)
        if (session.outputPath) args.push('--output', session.outputPath)
        break
      case 'yaml2pytest':
        args.push('yaml2pytest')
        if (session.interfacesDir) args.push('--interfaces', session.interfacesDir)
        if (session.singleCasesDir) args.push('--single-cases', session.singleCasesDir)
        if (session.bizFlowsDir) args.push('--biz-flows', session.bizFlowsDir)
        if (session.configDir) args.push('--config-dir', session.configDir)
        if (session.processorsDir) args.push('--processors-dir', session.processorsDir)
        if (session.outputPath) args.push('--output', session.outputPath)
        break
      case 'excel2pytest':
        args.push('excel2pytest')
        if (session.inputPath) args.push('--input', session.inputPath)
        if (session.configDir) args.push('--config-dir', session.configDir)
        if (session.processorsDir) args.push('--processors-dir', session.processorsDir)
        if (session.outputPath) args.push('--output', session.outputPath)
        break
    }

    return args
  }

  // ---- Subprocess lifecycle / 子进程生命周期 ----

  async function startSession(sessionId: string): Promise<void> {
    const session = sessions.value.find((s) => s.id === sessionId)
    if (!session) return

    session.status = 'running'
    session.logLines = []
    session.outputLinkPath = undefined
    session.error = undefined
    session.updatedAt = Date.now()

    const args = buildCliArgs(session)

    // 注册事件监听 / Register event listener
    const unlisten = listenToConverterEvents(sessionId, (line, level) => {
      appendLog(sessionId, level, line)
      tryParseCompletion(sessionId, line)
    })
    _listeners.set(sessionId, unlisten)

    // 启动子进程 / Spawn subprocess
    try {
      const agentStore = useAgentStore()
      // 确保 agent config 已从磁盘加载 / Ensure agent config is loaded from disk
      if (!agentStore.configLoaded) {
        await agentStore.loadConfig()
      }
      const cmd = resolvePythonCommand(agentStore.config)
      await spawnConverter(
        sessionId,
        agentStore.config.executorRootDir, // converter_main.py 位于 python/ 目录（与 executor main.py 同级） / converter_main.py is in python/ dir (alongside executor main.py)
        cmd.exe,
        cmd.preArgs,
        args,
      )
      appendLog(sessionId, 'info', 'Converter process started')
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
        const alive = await checkConverterRunning(sessionId)
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
      await killConverter(sessionId)
    } catch { /* already dead */ }

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
        session.outputLinkPath = parsed.output
        session.updatedAt = Date.now()
        _listeners.get(sessionId)?.()
        _listeners.delete(sessionId)
        const hc2 = _healthChecks.get(sessionId)
        if (hc2) { clearInterval(hc2); _healthChecks.delete(sessionId) }
        saveSessions()
      }
    } catch {
      // 不是 JSON 行，继续 / Not a JSON line, continue
    }
  }

  // ---- Init / 初始化 ----

  async function initialize(): Promise<void> {
    await loadSessions()
  }

  return {
    // State
    sessions,
    activeSessionId,
    // Getters
    activeSession,
    sortedSessions,
    // Actions
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
