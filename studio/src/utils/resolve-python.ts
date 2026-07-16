// Python 环境解析工具 / Python environment resolution utility
//
// 根据 AgentConfig 中的环境类型和路径配置，自动解析 Python 可执行文件路径。
// Resolves the Python executable path from AgentConfig based on env type.
import type { AgentConfig } from '../types/agent'

/**
 * 解析 Python 可执行文件路径。
 * Resolve the Python executable path from agent configuration.
 *
 * 优先级 / Priority:
 *   1. pythonExePath（手动覆盖 / manual override）— 如果非空直接返回
 *   2. envType==='venv': 从 venvPath 自动解析
 *      - Windows: {venvPath}/Scripts/python.exe
 *      - Unix/Mac: {venvPath}/bin/python
 *   3. envType==='conda': 使用 conda run 命令
 *      - conda run -n {condaEnvName} python
 *   4. 兜底 / Fallback: 'python'
 */
export function resolvePythonExe(config: AgentConfig, platform?: string): string {
  // 1. 手动覆盖优先 / Manual override takes precedence
  if (config.pythonExePath && config.pythonExePath.trim()) {
    return config.pythonExePath.trim()
  }

  const isWindows = (platform || (typeof navigator !== 'undefined' ? navigator.platform : '')).toLowerCase().includes('win')

  // 2. Python venv 模式 / Python venv mode
  if (config.envType === 'venv' && config.venvPath && config.venvPath.trim()) {
    const base = config.venvPath.trim().replace(/\\/g, '/').replace(/\/+$/, '')
    return isWindows ? `${base}/Scripts/python.exe` : `${base}/bin/python`
  }

  // 3. Conda 模式 / Conda mode
  // 使用 conda run 命令，无需知道 conda 安装路径
  // Use conda run command — doesn't require knowing conda install path
  if (config.envType === 'conda' && config.condaEnvName && config.condaEnvName.trim()) {
    const envName = config.condaEnvName.trim()
    return `conda run -n ${envName} python`
  }

  // 4. 兜底 / Fallback
  return 'python'
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
