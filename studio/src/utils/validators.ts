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
 * New format: JSON object / YAML mapping (Record<string, string>).
 * Old format (still accepted): comma-separated key1=value1, key2=value2...
 */
export function validateTrans(trans: Record<string, string> | string, stepId?: string): string | null {
  if (!trans) return null
  const idLabel = stepId ? ` (StepID="${stepId}")` : ''

  // Normalize to Record<string, string>
  let transObj: Record<string, string>
  if (typeof trans === 'string') {
    const stripped = trans.trim()
    if (!stripped) return null
    try {
      const parsed = JSON.parse(stripped)
      if (typeof parsed !== 'object' || Array.isArray(parsed)) {
        return `Trans 字段必须为 JSON 对象${idLabel}`
      }
      transObj = parsed as Record<string, string>
    } catch {
      // Fall back to old comma-separated format
      return validateTransOld(stripped, stepId)
    }
  } else {
    transObj = trans
  }

  // Validate each entry
  for (const [key, value] of Object.entries(transObj)) {
    if (!key.trim()) return `Trans 字段 key 为空${idLabel}`
    const v = String(value ?? '').trim()
    if (!v) return `Trans 字段 value 为空（key="${key}"）${idLabel}`
    if (CHINESE_RE.test(v)) return `Trans 字段包含中文字符${idLabel} (key="${key}": ${v})`
    for (const [open, close] of [['[', ']'], ['(', ')']] as [string, string][]) {
      const openCount = (v.match(new RegExp('\\' + open, 'g')) || []).length
      const closeCount = (v.match(new RegExp('\\' + close, 'g')) || []).length
      if (openCount !== closeCount) {
        return `Trans 字段括号不匹配 "${open}${close}"${idLabel} (key="${key}")`
      }
    }
  }
  return null
}

function validateTransOld(stripped: string, stepId?: string): string | null {
  const idLabel = stepId ? ` (StepID="${stepId}")` : ''

  if (CHINESE_RE.test(stripped)) {
    return `Trans 字段包含中文字符${idLabel}`
  }

  // Overall bracket matching
  for (const [open, close] of [['[', ']'], ['(', ')']] as [string, string][]) {
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

    if (!key) return `Trans 字段 key 为空${idLabel}: "${pair}"`
    if (!value) return `Trans 字段 value 为空（key="${key}"）${idLabel}`
  }
  return null
}

// ---------------------------------------------------------------------------
// Processor validation
// ---------------------------------------------------------------------------

export interface ProcessorValidationResult {
  valid: boolean
  error: string | null
}

export function validateProcessorItem(
  item: Record<string, unknown>
): ProcessorValidationResult {
  if (!item || typeof item !== 'object') {
    return { valid: false, error: '处理器项必须为对象' }
  }
  if (!item.name || typeof item.name !== 'string' || !item.name.trim()) {
    return { valid: false, error: '处理器项必须包含非空的 name 字段' }
  }
  if (item.config !== undefined && item.config !== null && typeof item.config !== 'object') {
    return { valid: false, error: '处理器 config 必须为对象或 null' }
  }
  return { valid: true, error: null }
}

export function validateProcessorsList(
  value: unknown
): ProcessorValidationResult {
  if (value === null || value === undefined) {
    return { valid: true, error: null }
  }
  if (!Array.isArray(value)) {
    return { valid: false, error: '处理器必须是 JSON 数组格式' }
  }
  for (let i = 0; i < value.length; i++) {
    const result = validateProcessorItem(value[i] as Record<string, unknown>)
    if (!result.valid) {
      return { valid: false, error: `第 ${i + 1} 项: ${result.error}` }
    }
  }
  return { valid: true, error: null }
}
