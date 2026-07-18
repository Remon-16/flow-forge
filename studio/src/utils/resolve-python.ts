// Python 环境解析工具 / Python environment resolution utility
//
// 根据 AgentConfig 中的环境类型和路径配置，自动解析 Python 可执行文件路径。
// Resolves the Python executable path from AgentConfig based on env type.
import type { AgentConfig } from '../types/agent'

// ============================================================================
// 平台缓存 / Platform cache
// ============================================================================

let _platformCache: string | null = null

/**
 * 初始化平台缓存，应在 app 启动时调用一次。
 * Initialize platform cache — call once at app startup.
 * 从 Rust 后端获取准确的 OS 平台标识，避免依赖 navigator.platform。
 * Gets accurate OS platform from Rust backend, avoiding navigator.platform dependency.
 */
export async function initPlatformCache(): Promise<void> {
  if (_platformCache) return
  try {
    const { getOsPlatform } = await import('./desktop-bridge')
    _platformCache = await getOsPlatform()
  } catch {
    // 回退：浏览器模式或 Rust 命令不可用时 / Fallback: browser mode or Rust command unavailable
    _platformCache = typeof navigator !== 'undefined' ? navigator.platform : ''
  }
}

// ============================================================================
// 接口 / Interfaces
// ============================================================================

/** 解析后的 Python 命令结构 / Resolved Python command structure */
export interface PythonCommand {
  /** 可执行文件路径 / Executable path */
  exe: string
  /** 在主 args 之前插入的前置参数（如 conda run -n env python）/ Pre-args inserted before main args */
  preArgs: string[]
}

// ============================================================================
// 解析函数 / Resolution functions
// ============================================================================

/**
 * 解析 Python 可执行文件路径。
 * Resolve the Python executable path from agent configuration.
 *
 * 优先级 / Priority:
 *   1. pythonExePath（手动覆盖 / manual override）— 如果非空直接返回
 *   2. envType==='venv': 从 venvPath 自动解析
 *      - Windows: {venvPath}/Scripts/python.exe
 *      - Unix/Mac: {venvPath}/bin/python
 *   3. envType==='conda': 使用 conda run 命令（仅用于显示预览）
 *      - conda run -n {condaEnvName} python
 *      - 注意：此函数返回的 conda 字符串仅供显示，实际子进程启动应使用 resolvePythonCommand
 *   4. 兜底 / Fallback: 'python'
 */
export function resolvePythonExe(config: AgentConfig, platform?: string): string {
  // 1. 手动覆盖优先 / Manual override takes precedence
  if (config.pythonExePath && config.pythonExePath.trim()) {
    return config.pythonExePath.trim()
  }

  const isWindows = (platform || _platformCache || (typeof navigator !== 'undefined' ? navigator.platform : '')).toLowerCase().includes('win')

  // 2. Python venv 模式 / Python venv mode
  if (config.envType === 'venv' && config.venvPath && config.venvPath.trim()) {
    const base = config.venvPath.trim().replace(/\\/g, '/').replace(/\/+$/, '')
    return isWindows ? `${base}/Scripts/python.exe` : `${base}/bin/python`
  }

  // 3. Conda 模式 / Conda mode
  // 使用 conda run 命令，无需知道 conda 安装路径
  // Use conda run command — doesn't require knowing conda install path
  // 注意：返回值为显示预览用，子进程启动请使用 resolvePythonCommand
  // Note: returned string is for display/preview; use resolvePythonCommand for spawning
  if (config.envType === 'conda' && config.condaEnvName && config.condaEnvName.trim()) {
    const envName = config.condaEnvName.trim()
    return `conda run -n ${envName} python`
  }

  // 4. 兜底 / Fallback
  return 'python'
}

/**
 * 解析 Python 可执行文件路径和前置参数，用于子进程启动。
 * Resolve Python executable and pre-args for subprocess spawning.
 *
 * 与 resolvePythonExe 不同，此函数对 conda 环境返回拆分后的结构化命令，
 * 确保 Rust 端的 Command::new() 能正确接收可执行文件名和参数。
 * Unlike resolvePythonExe, returns structured command for conda environments
 * so that Command::new() on the Rust side receives the correct exe + args.
 *
 * 优先级与 resolvePythonExe 相同 / Same priority as resolvePythonExe:
 *   1. pythonExePath（手动覆盖 / manual override）
 *   2. venv: {venvPath}/Scripts/python.exe 或 {venvPath}/bin/python
 *   3. conda: exe="conda", preArgs=["run", "-n", envName, "python"]
 *   4. 兜底 / Fallback: 'python'
 */
export function resolvePythonCommand(config: AgentConfig, platform?: string): PythonCommand {
  // 1. 手动覆盖优先 / Manual override takes precedence
  if (config.pythonExePath && config.pythonExePath.trim()) {
    return { exe: config.pythonExePath.trim(), preArgs: [] }
  }

  const isWindows = (platform || _platformCache || (typeof navigator !== 'undefined' ? navigator.platform : '')).toLowerCase().includes('win')

  // 2. Python venv 模式 / Python venv mode
  if (config.envType === 'venv' && config.venvPath && config.venvPath.trim()) {
    const base = config.venvPath.trim().replace(/\\/g, '/').replace(/\/+$/, '')
    return {
      exe: isWindows ? `${base}/Scripts/python.exe` : `${base}/bin/python`,
      preArgs: [],
    }
  }

  // 3. Conda 模式 — 拆分为 exe + 前置参数，确保 Rust Command::new 正确解析
  // Conda mode — split into exe + pre-args so Rust Command::new parses correctly
  if (config.envType === 'conda' && config.condaEnvName && config.condaEnvName.trim()) {
    const envName = config.condaEnvName.trim()
    return { exe: 'conda', preArgs: ['run', '-n', envName, 'python'] }
  }

  // 4. 兜底 / Fallback
  return { exe: 'python', preArgs: [] }
}

/**
 * 获取环境类型的显示标签。
 * Get human-readable label for environment type.
 */
export function getEnvTypeLabel(envType: string): string {
  switch (envType) {
    case 'system': return 'System Python'
    case 'venv':   return 'Python venv'
    case 'conda':  return 'Conda'
    default:       return envType
  }
}
