// 运算符模式 — 按优先级排序（最长模式优先以避免歧义）。
// Operator patterns — priority-ordered (longest first to avoid ambiguity).
// 注意: 正则表达式是 TypeScript 特定的，与 Python 版本语法不同。
// Note: regex patterns are TypeScript-specific, syntax differs from Python version.
const OPERATOR_PATTERNS: { op: string; regex: RegExp; needsExpected: boolean }[] = [
  { op: 'is_not_null',  regex: /\s+is_not_null\s*$/i,       needsExpected: false },
  { op: 'is_null',      regex: /\s+is_null\s*$/i,           needsExpected: false },
  { op: 'typeof',       regex: /\s+typeof\s+/i,             needsExpected: true },
  { op: 'not_contains', regex: /\s+not_contains\s+/i,       needsExpected: true },
  { op: 'contains',     regex: /\s+contains\s+/i,           needsExpected: true },
  { op: 'in',           regex: /\s+in\s+/i,                 needsExpected: true },
  { op: '!=',           regex: /\s*!=\s*/,                  needsExpected: true },
  { op: '==',           regex: /\s*==\s*/,                  needsExpected: true },
  { op: '>=',           regex: /\s*>=\s*/,                  needsExpected: true },
  { op: '<=',           regex: /\s*<=\s*/,                  needsExpected: true },
  { op: '=~',           regex: /\s*=~\s*/,                  needsExpected: true },
  { op: '>',            regex: /\s*>\s*/,                   needsExpected: true },
  { op: '<',            regex: /\s*<\s*/,                   needsExpected: true },
]

import { VALID_FUNCTIONS, VALID_TYPES } from '@flow-forge-schemas'

export interface AssertRuleParsed {
  raw: string
  path: string
  operator: string
  expected: string
  error: string | null
}

export function validateAssertRule(ruleStr: string): AssertRuleParsed {
  const raw = ruleStr.trim()

  // Empty rule is valid (optional field)
  if (!raw) {
    return { raw, path: '', operator: '', expected: '', error: null }
  }

  // Try each operator pattern in priority order
  for (const { op, regex, needsExpected } of OPERATOR_PATTERNS) {
    const match = raw.match(regex)
    if (!match) continue

    const idx = match.index!
    const path = raw.substring(0, idx).trim()

    // For is_null / is_not_null, the operator consumes the rest
    let expected = ''
    if (needsExpected) {
      expected = raw.substring(idx + match[0].length).trim()
    } else {
      // For no-expected operators, the rest after path should be just the operator
      const afterPath = raw.substring(idx).trim()
      if (afterPath.toLowerCase() !== op.toLowerCase()) {
        continue // operator text doesn't match cleanly
      }
    }

    // Validate path
    const pathErr = validatePath(path)
    if (pathErr) return { raw, path: '', operator: '', expected: '', error: pathErr }

    // Validate expected value
    if (needsExpected && !expected) {
      return { raw, path: '', operator: '', expected: '', error: 'Missing expected value' }
    }

    // For typeof, validate the type name
    if (op === 'typeof' && expected && !VALID_TYPES.includes(expected)) {
      return { raw, path: '', operator: '', expected: '', error: `Unknown type: "${expected}". Valid types: ${VALID_TYPES.join(', ')}` }
    }

    return { raw, path, operator: op, expected, error: null }
  }

  // No operator matched
  return { raw, path: '', operator: '', expected: '', error: 'Format error: expected "PATH OPERATOR [EXPECTED]"' }
}

function validatePath(path: string): string | null {
  if (!path) return 'Path cannot be empty'

  // More permissive validation for complex paths with functions
  const hasFunctionCall = /[A-Z_]+\(.+\)/.test(path)

  if (hasFunctionCall) {
    // For function calls like SUM($.data.list[*].price), validate the inner path
    const funcMatch = path.match(/^(SUM_PRODUCT|SUM)\((.+)\)$/)
    if (funcMatch) {
      const funcName = funcMatch[1]
      const args = funcMatch[2].split(',').map(s => s.trim())

      if (!VALID_FUNCTIONS.includes(funcName)) {
        return `Unknown function: "${funcName}"`
      }

      for (const arg of args) {
        const err = validateSimplePath(arg)
        if (err) return err
      }

      return null
    }

    return `Unrecognized function call syntax: "${path}"`
  }

  // Simple path validation
  return validateSimplePath(path)
}

function validateSimplePath(path: string): string | null {
  // Allow: $.a.b.c, data.list[0].name, $.data.items[*].price, $.data.list.length()
  // Strip leading $.
  let p = path.replace(/^\$\./, '')

  // Handle .length() suffix
  if (p.endsWith('.length()')) {
    p = p.slice(0, -'.length()'.length)
  }

  if (!p) {
    // Just "$" or empty is too short
    return null
  }

  const parts = p.split('.')
  for (const part of parts) {
    // Match: identifier or identifier[index] or identifier[*]
    const m = part.match(/^([a-zA-Z_]\w*)((?:\[\d+\]|\[\*\])*)$/)
    if (!m) {
      return `Path syntax error at "${part}"`
    }
  }

  // Check bracket balance
  const openBrackets = (path.match(/\[/g) || []).length
  const closeBrackets = (path.match(/\]/g) || []).length
  if (openBrackets !== closeBrackets) {
    return 'Mismatched brackets in path'
  }

  // Check paren balance
  const openParens = (path.match(/\(/g) || []).length
  const closeParens = (path.match(/\)/g) || []).length
  if (openParens !== closeParens) {
    return 'Mismatched parentheses in path'
  }

  return null
}

export function validateAssertRulesList(rules: string[] | null): { valid: boolean; errors: string[] } {
  if (!rules || rules.length === 0) return { valid: true, errors: [] }

  const errors: string[] = []
  for (let i = 0; i < rules.length; i++) {
    const result = validateAssertRule(rules[i])
    if (result.error) {
      errors.push(`Rule ${i + 1}: ${result.error}`)
    }
  }

  return { valid: errors.length === 0, errors }
}
