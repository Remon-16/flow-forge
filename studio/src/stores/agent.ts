// Agent Store — Pinia store for agent task management.
// 智能体存储 — 管理 agent 任务、配置和子进程通信的 Pinia store。

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type {
  AgentTask,
  AgentConfig,
  LogEntry,
  AgentEvent,
  AgentCommand,
  CompletionSummary,
} from '../types/agent'
import { spawnAgent, sendToAgent, killAgent, checkAgentRunning, listenToAgentEvents } from '../utils/agent-bridge'
import { resolvePythonCommand } from '../utils/resolve-python'
import { loadSettingsFile, saveSettingsFile } from '../utils/settings-store'
import { fixStaleRunningStatus, STALE_STATUS_ERROR_MSG } from '../utils/process-liveness'

const CONFIG_FILE = 'agent_config.json'
const REGISTRY_FILE = 'agent_tasks.json'

// ============================================================================
// 默认值 / Defaults
// ============================================================================

const DEFAULT_CONFIG: AgentConfig = {
  agentRootDir: '',
  pythonExePath: '',
  venvPath: '',
  executorRootDir: '',
  saveToEnvFile: false,
  envType: 'system',
  condaEnvName: '',
}

// ============================================================================
// Store / 存储
// ============================================================================

export const useAgentStore = defineStore('agent', () => {
  // ---- State / 状态 ----

  const config = ref<AgentConfig>({ ...DEFAULT_CONFIG })
  const configLoaded = ref(false)

  const tasks = ref<AgentTask[]>([])
  const activeTaskId = ref<string | null>(null)
  const unreadPrompts = ref<Set<string>>(new Set())

  // 每个运行中任务的 listener 清理函数 / Listener cleanup per running task
  const _listeners = new Map<string, () => void>()

  // 每个运行中任务的健康检查 interval / Health check interval per running task
  const _healthChecks = new Map<string, ReturnType<typeof setInterval>>()

  // ---- Getters / 计算属性 ----

  const activeTask = computed(() =>
    tasks.value.find((t) => t.id === activeTaskId.value) ?? null,
  )

  const sortedTasks = computed(() =>
    [...tasks.value].sort((a, b) => b.updatedAt - a.updatedAt),
  )

  const hasUnreadPrompts = computed(() => unreadPrompts.value.size > 0)

  // ---- Config actions / 配置操作 ----

  async function loadConfig(): Promise<void> {
    config.value = await loadSettingsFile(CONFIG_FILE, DEFAULT_CONFIG)
    configLoaded.value = true
  }

  /**
   * 保存配置并标记需要重新加载。
   * Save config and mark for reload.
   * 重置 configLoaded 确保下次读取时从磁盘重新加载最新数据。
   * Reset configLoaded to ensure fresh data is read from disk next time.
   */
  async function saveConfig(): Promise<void> {
    await saveSettingsFile(CONFIG_FILE, config.value)
    // 标记需要重新加载，防止 getExecutorRootDir 等函数使用过期内存数据
    // Mark for reload to prevent stale in-memory data in getExecutorRootDir etc.
    configLoaded.value = false
  }

  // ---- Task registry actions / 任务注册表操作 ----

  async function loadTaskRegistry(): Promise<void> {
    const saved = await loadSettingsFile<AgentTask[]>(REGISTRY_FILE, [])
    tasks.value = saved
  }

  async function saveTaskRegistry(): Promise<void> {
    await saveSettingsFile(REGISTRY_FILE, tasks.value)
  }

  // ---- Task management / 任务管理 ----

  async function createTask(params: {
    outputDir: string
    requirementPaths: string
    apiPaths: string
    autoMode: boolean
    userGuidance: string
    caseType: 'single' | 'biz' | 'both'
  }): Promise<string> {
    const id = `task_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
    const name = params.outputDir.split(/[/\\]/).pop() || params.outputDir

    const task: AgentTask = {
      id,
      name,
      outputDir: params.outputDir.replace(/\\/g, '/'),
      status: 'pending',
      createdAt: Date.now(),
      updatedAt: Date.now(),
      requirementPaths: params.requirementPaths,
      apiPaths: params.apiPaths,
      autoMode: params.autoMode,
      userGuidance: params.userGuidance,
      caseType: params.caseType,
      logLines: [],
    }

    tasks.value.unshift(task)
    activeTaskId.value = id
    await saveTaskRegistry()
    return id
  }

  async function removeTask(taskId: string): Promise<void> {
    // 先终止正在运行的进程 / Kill running process first
    if (_listeners.has(taskId)) {
      await killAgent(taskId)
      _listeners.get(taskId)?.()
      _listeners.delete(taskId)
      // 同步清理健康检查 / Clean up health check too
      const hc = _healthChecks.get(taskId)
      if (hc) { clearInterval(hc); _healthChecks.delete(taskId) }
    }

    tasks.value = tasks.value.filter((t) => t.id !== taskId)
    if (activeTaskId.value === taskId) {
      activeTaskId.value = tasks.value[0]?.id ?? null
    }
    unreadPrompts.value.delete(taskId)
    await saveTaskRegistry()
  }

  function selectTask(taskId: string | null): void {
    activeTaskId.value = taskId
    if (taskId) {
      unreadPrompts.value.delete(taskId)
    }
  }

  // ---- Task execution / 任务执行 ----

  async function startTask(taskId: string, cliArgs: string[]): Promise<void> {
    const task = tasks.value.find((t) => t.id === taskId)
    if (!task) return

    task.status = 'running'
    task.logLines = []
    task.pendingPrompt = undefined
    task.error = undefined
    task.updatedAt = Date.now()

    // 构建额外 CLI 参数 / Build additional CLI args
    // 多路径以 ; 或空格分隔 / Multi-path separated by ; or space
    const reqPaths = task.requirementPaths ? task.requirementPaths.split(/[;\n]+/).map(s => s.trim()).filter(Boolean) : []
    const apiPathList = task.apiPaths ? task.apiPaths.split(/[;\n]+/).map(s => s.trim()).filter(Boolean) : []

    const args: string[] = [
      '--output', task.outputDir,
      ...(reqPaths.length ? ['--requirement', ...reqPaths] : []),
      ...(apiPathList.length ? ['--api', ...apiPathList] : []),
      ...(task.autoMode ? ['--auto'] : []),
      ...(task.userGuidance ? ['--prompt', task.userGuidance] : []),
      '--case-type', task.caseType,
      ...cliArgs,
    ]

    // 注册事件监听（先 await 监听器就绪，再 spawn 进程，防止事件丢失）
    // Register event listener (await listener readiness before spawn to prevent event loss)
    const unlisten = await listenToAgentEvents(taskId, (event: AgentEvent) => {
      handleAgentEvent(taskId, event)
    })
    _listeners.set(taskId, unlisten)

    // Spawn subprocess / 启动子进程
    try {
      const cmd = resolvePythonCommand(config.value)
      await spawnAgent(
        taskId,
        config.value.agentRootDir,
        cmd.exe,
        cmd.preArgs,
        args,
      )
      appendLog(taskId, 'info', 'Agent process started')
      _startHealthCheck(taskId)
    } catch (e: any) {
      task.status = 'error'
      task.error = e?.message || String(e)
      appendLog(taskId, 'error', `Failed to start: ${task.error}`)
      _listeners.get(taskId)?.()
      _listeners.delete(taskId)
    }

    await saveTaskRegistry()
  }

  async function startResumeTask(taskId: string, cliArgs: string[]): Promise<void> {
    const task = tasks.value.find((t) => t.id === taskId)
    if (!task) return

    task.status = 'running'
    task.logLines = []
    task.pendingPrompt = undefined
    task.error = undefined
    task.updatedAt = Date.now()

    const args: string[] = [
      '--resume',
      '--output', task.outputDir,
      ...cliArgs,
    ]

    // 注册事件监听（先 await 监听器就绪，再 spawn 进程，防止事件丢失）
    // Register event listener (await listener readiness before spawn to prevent event loss)
    const unlisten = await listenToAgentEvents(taskId, (event: AgentEvent) => {
      handleAgentEvent(taskId, event)
    })
    _listeners.set(taskId, unlisten)

    try {
      const cmd = resolvePythonCommand(config.value)
      await spawnAgent(
        taskId,
        config.value.agentRootDir,
        cmd.exe,
        cmd.preArgs,
        args,
      )
      appendLog(taskId, 'info', 'Agent process started (resume mode)')
      _startHealthCheck(taskId)
    } catch (e: any) {
      task.status = 'error'
      task.error = e?.message || String(e)
      appendLog(taskId, 'error', `Failed to start: ${task.error}`)
      _listeners.get(taskId)?.()
      _listeners.delete(taskId)
    }

    await saveTaskRegistry()
  }

  // ---- Agent event handling / Agent 事件处理 ----

  function handleAgentEvent(taskId: string, event: AgentEvent): void {
    const task = tasks.value.find((t) => t.id === taskId)
    if (!task) return

    switch (event.type) {
      case 'log':
        appendLog(taskId, event.level as LogEntry['level'], event.message)
        break

      case 'progress':
        appendLog(taskId, 'info', `[${event.stage || ''}] ${event.detail || ''}`)
        break

      case 'prompt':
        task.status = 'question'
        task.pendingPrompt = event as any
        // 如果不是当前活跃任务，标记未读 / Mark unread if not active
        if (activeTaskId.value !== taskId) {
          unreadPrompts.value = new Set([...unreadPrompts.value, taskId])
        }
        appendLog(taskId, 'info', `[Prompt] ${event.kind}: ${event.message}`)
        break

      case 'complete':
        task.status = 'completed'
        task.summary = (event as any).data as CompletionSummary
        task.pendingPrompt = undefined
        appendLog(taskId, 'info', 'Pipeline completed successfully')
        cleanupListener(taskId)
        break

      case 'error':
        task.status = 'error'
        task.error = event.message
        appendLog(taskId, 'error', event.message)
        cleanupListener(taskId)
        break
    }

    task.updatedAt = Date.now()
    saveTaskRegistry()
  }

  function appendLog(taskId: string, level: LogEntry['level'], message: string): void {
    const task = tasks.value.find((t) => t.id === taskId)
    if (!task) return
    task.logLines.push({
      ts: new Date().toLocaleTimeString(),
      level,
      message,
    })
  }

  // ---- Agent commands / Agent 命令 ----

  async function sendCommand(taskId: string, command: AgentCommand): Promise<void> {
    const task = tasks.value.find((t) => t.id === taskId)
    if (!task) return
    // 清除 prompt 状态 / Clear prompt state
    task.status = 'running'
    task.pendingPrompt = undefined
    task.updatedAt = Date.now()
    await sendToAgent(taskId, JSON.stringify(command))
  }

  async function terminateTask(taskId: string): Promise<void> {
    const task = tasks.value.find((t) => t.id === taskId)
    if (!task) return
    task.status = 'error'
    task.error = 'Terminated by user'
    task.updatedAt = Date.now()
    appendLog(taskId, 'info', 'Task terminated by user')

    try {
      await killAgent(taskId)
    } catch { /* process may already be dead */ }

    cleanupListener(taskId)
    await saveTaskRegistry()
  }

  // ---- Cleanup / 清理 ----

  /**
   * 启动进程健康检查 — 每 5 秒检查子进程是否存活。
   * Start process health check — poll every 5s to see if subprocess is still alive.
   * 若进程已退出但状态仍为 running，标记为 error（进程可能崩溃）。
   * If the process exited but status is still running, mark as error (process may have crashed).
   */
  function _startHealthCheck(taskId: string): void {
    const interval = setInterval(async () => {
      const t = tasks.value.find(x => x.id === taskId)
      if (!t || t.status !== 'running') {
        clearInterval(interval)
        _healthChecks.delete(taskId)
        return
      }
      try {
        const alive = await checkAgentRunning(taskId)
        if (!alive) {
          t.status = 'error'
          t.error = 'Process exited unexpectedly'
          appendLog(taskId, 'error', 'Process exited unexpectedly — 进程可能已崩溃 / may have crashed')
          cleanupListener(taskId)
          clearInterval(interval)
          _healthChecks.delete(taskId)
          await saveTaskRegistry()
        }
      } catch { /* 忽略检查错误 / ignore check errors */ }
    }, 5000)
    _healthChecks.set(taskId, interval)
  }

  function cleanupListener(taskId: string): void {
    _listeners.get(taskId)?.()
    _listeners.delete(taskId)
    // 清理健康检查 / Clean up health check
    const hc = _healthChecks.get(taskId)
    if (hc) {
      clearInterval(hc)
      _healthChecks.delete(taskId)
    }
  }

  // ---- Validation / 校验 ----

  /** 检查所有任务的输出目录是否存在，移除不存在的 / Verify all output dirs, remove stale */
  async function validateOutputDirs(): Promise<void> {
    const { exists } = await import('../utils/desktop-bridge')
    const valid: AgentTask[] = []
    for (const task of tasks.value) {
      try {
        const dirExists = await exists(task.outputDir)
        if (dirExists) {
          valid.push(task)
        }
      } catch {
        // 浏览器模式下保留所有任务 / In browser mode, keep all tasks
        valid.push(task)
      }
    }
    if (valid.length < tasks.value.length) {
      tasks.value = valid
      await saveTaskRegistry()
    }
  }

  // ---- Init / 初始化 ----

  async function initialize(): Promise<void> {
    // 幂等保护：已初始化则跳过 / Idempotent guard: skip if already initialized
    if (configLoaded.value) return
    await loadConfig()
    await loadTaskRegistry()
    // 修复启动时卡在 running/question 状态的旧任务 / Fix stale running/question tasks on startup
    if (await fixStaleRunningStatus(
      tasks.value,
      checkAgentRunning,
      ['running', 'question'],
      STALE_STATUS_ERROR_MSG,
    )) {
      // 为被修复的项添加日志 / Add log for fixed items
      for (const task of tasks.value) {
        if (task.error === STALE_STATUS_ERROR_MSG) {
          appendLog(task.id, 'error', '任务状态已修正：进程已丢失（Studio 关闭或崩溃）/ Task status corrected: process lost (Studio was closed or crashed)')
        }
      }
      await saveTaskRegistry()
    }
    // 后台验证目录，不阻塞 UI / Validate dirs in background
    validateOutputDirs()
  }

  return {
    // State
    config,
    configLoaded,
    tasks,
    activeTaskId,
    unreadPrompts,
    // Getters
    activeTask,
    sortedTasks,
    hasUnreadPrompts,
    // Actions
    loadConfig,
    saveConfig,
    loadTaskRegistry,
    saveTaskRegistry,
    createTask,
    removeTask,
    selectTask,
    startTask,
    startResumeTask,
    sendCommand,
    terminateTask,
    validateOutputDirs,
    initialize,
  }
})
