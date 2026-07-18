// 日志级别解析 — 从 Python stderr 行中提取日志级别和显示文本。
// Log level parser — extract level and display text from Python stderr lines.
//
// Python 端（shared/py/flow_forge_logging）在 Studio 模式下输出 JSON：
// Python side (shared/py/flow_forge_logging) outputs JSON in Studio mode:
//   {"type":"log","level":"info","message":"HH:MM:SS [INFO] name: msg"}
//
// 兜底策略：非 JSON 行直接视为 info 级别，原文显示。
// Fallback: non-JSON lines default to info level, displayed as-is.

// ============================================================================
// 类型定义 / Type definitions
// ============================================================================

export interface ParsedStderrLine {
  level: 'info' | 'warn' | 'error'
  /** 用于界面显示的文本（JSON 行提取 message 字段，非 JSON 行原文返回）
   *  Display text (extracted message field for JSON lines, raw text for others) */
  message: string
}

// ============================================================================
// 解析函数 / Parse function
// ============================================================================

/**
 * 解析 stderr 行，返回级别和显示文本。
 * Parse a stderr line, returning level and display message.
 *
 * 优先 JSON 解析（Studio 模式），非 JSON 行按 info 兜底。
 * Prefers JSON parse (Studio mode); non-JSON lines default to info.
 *
 * @param line - stderr 原始行文本 / raw stderr line text
 * @returns 解析结果，包含 level 和 message / parsed result with level and message
 */
export function parseStderrLine(line: string): ParsedStderrLine {
  // 尝试 JSON 解析（Studio 模式下 Python 输出 JSON 行）
  // Try JSON parse (Python outputs JSON lines in Studio mode)
  if (line.startsWith('{')) {
    try {
      const parsed = JSON.parse(line)
      if (parsed.type === 'log' && parsed.message) {
        const level = parsed.level
        if (level === 'warn' || level === 'warning') {
          return { level: 'warn', message: parsed.message }
        }
        if (level === 'error' || level === 'critical') {
          return { level: 'error', message: parsed.message }
        }
        return { level: 'info', message: parsed.message }
      }
    } catch {
      // JSON 解析失败 → 兜底 / Parse failure → fallback
    }
  }
  // 非 JSON 行或解析失败 → 默认 info
  // Non-JSON line or parse failure → default to info
  return { level: 'info', message: line }
}
