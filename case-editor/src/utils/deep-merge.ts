/**
 * Recursively merge two objects.
 * Keys present in both: if both values are objects, merge recursively.
 * Otherwise, override wins.
 * Keys only in base are preserved; keys only in override are added.
 * Returns a new object — neither input is mutated.
 * Aligns with python/core/deep_merge.py.
 */
export function deepMerge(
  base: Record<string, unknown>,
  override: Record<string, unknown>
): Record<string, unknown> {
  if (!base) return deepClone(override ?? {})
  if (!override) return deepClone(base)

  const result = deepClone(base)
  for (const [key, val] of Object.entries(override)) {
    if (
      key in result &&
      typeof result[key] === 'object' &&
      result[key] !== null &&
      !Array.isArray(result[key]) &&
      typeof val === 'object' &&
      val !== null &&
      !Array.isArray(val)
    ) {
      result[key] = deepMerge(
        result[key] as Record<string, unknown>,
        val as Record<string, unknown>
      )
    } else {
      result[key] = deepClone(val)
    }
  }
  return result
}

function deepClone<T>(obj: T): T {
  if (obj === null || typeof obj !== 'object') return obj
  return JSON.parse(JSON.stringify(obj))
}
