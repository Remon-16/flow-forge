const CHINESE_RE = /[一-鿿㐀-䶿豈-﫿]/

/**
 * Validate RelevanceID against available TestID values from the API definitions sheet.
 */
export function validateRelevanceID(
  relevanceId: string,
  validTestIds: string[]
): string | null {
  if (!relevanceId || !relevanceId.trim()) {
    return 'RelevanceID 不能为空'
  }
  if (!validTestIds.includes(relevanceId.trim())) {
    return `RelevanceID "${relevanceId}" 在接口定义页中不存在`
  }
  return null
}

/**
 * Check for duplicate StepIDs within a biz flow sheet.
 * Returns a Set of duplicate StepIDs.
 */
export function findDuplicateStepIDs(
  steps: { StepID: string }[]
): Set<string> {
  const ids = steps.map((s) => s.StepID?.trim()).filter(Boolean)
  const seen = new Set<string>()
  const dupes = new Set<string>()
  for (const id of ids) {
    if (seen.has(id)) {
      dupes.add(id)
    } else {
      seen.add(id)
    }
  }
  return dupes
}

/**
 * Validate a Trans field value.
 * Returns null if valid, or an error message string if invalid.
 *
 * Format: key1=value1, key2=value2...
 * - Brackets must match: [] and ()
 * - No Chinese characters allowed
 * - Each pair must have non-empty key and value
 */
export function validateTrans(transStr: string, stepId?: string): string | null {
  if (!transStr) return null
  const stripped = transStr.trim()
  if (!stripped) return null

  const idLabel = stepId ? ` (StepID="${stepId}")` : ''

  // Chinese character check
  if (CHINESE_RE.test(stripped)) {
    return `Trans 字段包含中文字符${idLabel}`
  }

  // Overall bracket matching
  const brackets: [string, string][] = [
    ['[', ']'],
    ['(', ')'],
  ]
  for (const [open, close] of brackets) {
    const openCount = (stripped.match(new RegExp('\\' + open, 'g')) || []).length
    const closeCount = (stripped.match(new RegExp('\\' + close, 'g')) || []).length
    if (openCount !== closeCount) {
      return `Trans 字段括号不匹配 "${open}${close}"${idLabel}`
    }
  }

  // Per-pair validation
  const pairs = stripped.split(',').map((p) => p.trim()).filter(Boolean)
  for (const pair of pairs) {
    if (!pair.includes('=')) {
      return `Trans 格式错误（应为 key=value）${idLabel}: "${pair}"`
    }
    const eqIdx = pair.indexOf('=')
    const key = pair.slice(0, eqIdx).trim()
    const value = pair.slice(eqIdx + 1).trim()

    if (!key) {
      return `Trans 字段 key 为空${idLabel}: "${pair}"`
    }
    if (!value) {
      return `Trans 字段 value 为空（key="${key}"）${idLabel}`
    }
  }

  return null
}
