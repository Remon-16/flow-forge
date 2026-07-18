// 字符串命名风格转换工具函数。
// String naming convention conversion utilities.

/**
 * 将 snake_case 字符串转换为 camelCase。
 * Convert a snake_case string to camelCase.
 *
 * 例如 / e.g.: max_steps → maxSteps, log_to_output → logToOutput
 */
export function snakeToCamel(s: string): string {
  return s.replace(/_([a-z])/g, (_, letter: string) => letter.toUpperCase())
}
