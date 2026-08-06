/** 路径工具函数 / Path utility functions.
 *
 * 统一所有路径为正斜杠格式，避免 Windows 反斜杠与硬编码正斜杠混合。
 * Normalize all paths to forward-slash format to avoid mixing Windows
 * backslashes with hardcoded forward slashes.
 */

/** 规范化路径中的所有分隔符为正斜杠 / Normalize all path separators to forward slashes. */
export function normalizePath(p: string): string {
  return p.replace(/\\/g, '/')
}

/** 使用正斜杠连接路径段 / Join path segments with forward slash.
 *
 * 每个段先规范化，再去除首尾多余斜杠，最后用 "/" 连接。
 * Each segment is normalized, trimmed of excess leading/trailing slashes,
 * then joined with "/".
 */
export function joinPath(...segments: string[]): string {
  return segments
    .map(s => normalizePath(s).replace(/\/+$/, '').replace(/^\/+/, ''))
    .filter(Boolean)
    .join('/')
}
