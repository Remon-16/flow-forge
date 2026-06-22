import yaml from 'js-yaml'
import { toRaw } from 'vue'
import type { YamlCase, SingleYamlCase, BizYamlCase, InterfaceYamlCase } from '../types/yaml'
import type { PreProcessorItem, PostProcessorItem } from '../types/excel'

/**
 * Parse a YAML string into a YamlCase object.
 */
export function parseYaml(content: string): YamlCase {
  const obj = yaml.load(content) as Record<string, unknown> | null
  if (!obj || typeof obj !== 'object') {
    throw new Error('YAML content is empty or not an object')
  }

  const caseType = obj['case_type']
  if (caseType === 'single') {
    return normalizeSingleCase(obj)
  } else if (caseType === 'biz') {
    return normalizeBizCase(obj)
  } else if (caseType === 'interfaces') {
    return normalizeInterfaceCase(obj)
  }

  throw new Error(`Unknown case_type: "${caseType}". Expected "single", "biz", or "interfaces".`)
}

/**
 * Serialize a YamlCase object to a YAML string.
 */
export function stringifyYaml(data: YamlCase): string {
  try {
    const raw = toRaw(data)
    const cloned = JSON.parse(JSON.stringify(raw)) as Record<string, unknown>
    const clean = cleanNulls(cloned)
    return yaml.dump(clean, {
      indent: 2,
      lineWidth: -1,
      noRefs: true,
      sortKeys: false,
      flowLevel: -1,
    })
  } catch (err) {
    console.error('stringifyYaml failed:', err instanceof Error ? err.message : err)
    return '# Error serializing YAML'
  }
}

function normalizeSingleCase(raw: Record<string, unknown>): SingleYamlCase {
  return {
    case_type: 'single',
    test_id: String(raw['test_id'] ?? ''),
    relevance_id: String(raw['relevance_id'] ?? ''),
    tag: String(raw['tag'] ?? 'P0'),
    api_name: String(raw['api_name'] ?? ''),
    app_name: String(raw['app_name'] ?? ''),
    method: String(raw['method'] ?? 'GET'),
    url: String(raw['url'] ?? ''),
    request_head: asObject(raw['request_head']),
    request_body: asObject(raw['request_body']),
    status_code: (raw['status_code'] as string | number) ?? 200,
    assert_dict: asObject(raw['assert_dict']),
    assert_rules: asStringArray(raw['assert_rules']),
    preprocessors: asProcessorArray(raw['preprocessors']),
    postprocessors: asProcessorArray(raw['postprocessors']),
    remark: String(raw['remark'] ?? ''),
  }
}

function getField(raw: Record<string, unknown>, pascal: string, snake: string): unknown {
  if (pascal in raw) return raw[pascal]
  return raw[snake]
}

function normalizeTrans(val: unknown): Record<string, string> {
  if (val === null || val === undefined) return {}
  if (typeof val === 'object' && !Array.isArray(val)) return val as Record<string, string>
  if (typeof val === 'string') {
    if (!val.trim()) return {}
    try {
      const parsed = JSON.parse(val)
      if (typeof parsed === 'object' && !Array.isArray(parsed)) return parsed as Record<string, string>
    } catch {
      return transStringToObj(val)
    }
    return {}
  }
  return {}
}

function transStringToObj(s: string): Record<string, string> {
  const result: Record<string, string> = {}
  const pairs = s.split(',').map(p => p.trim()).filter(Boolean)
  for (const pair of pairs) {
    const eqIdx = pair.indexOf('=')
    if (eqIdx < 0) continue
    const key = pair.slice(0, eqIdx).trim()
    const value = pair.slice(eqIdx + 1).trim()
    if (key && value) result[key] = value
  }
  return result
}

function normalizeBizCase(raw: Record<string, unknown>): BizYamlCase {
  const stepsVal = getField(raw, 'steps', 'Steps')
  const rawSteps = Array.isArray(stepsVal) ? stepsVal as Record<string, unknown>[] : []
  return {
    case_type: 'biz',
    sheet_name: String(getField(raw, 'SheetName', 'sheet_name') ?? ''),
    steps: rawSteps.map(normalizeBizStep),
  }
}

function normalizeBizStep(raw: Record<string, unknown>): any {
  return {
    step_id: String(getField(raw, 'StepID', 'step_id') ?? ''),
    relevance_id: String(getField(raw, 'RelevanceID', 'relevance_id') ?? ''),
    trans: normalizeTrans(getField(raw, 'Trans', 'trans')),
    api_name: String(getField(raw, 'APIName', 'api_name') ?? ''),
    app_name: String(getField(raw, 'AppName', 'app_name') ?? ''),
    method: String(getField(raw, 'Method', 'method') ?? 'GET'),
    url: String(getField(raw, 'URL', 'url') ?? ''),
    request_head: asObject(getField(raw, 'RequestHead', 'request_head')),
    request_body: asObject(getField(raw, 'RequestBody', 'request_body')),
    status_code: getField(raw, 'StatusCode', 'status_code') ?? 200,
    assert_dict: asObject(getField(raw, 'AssertDict', 'assert_dict')),
    assert_rules: asStringArray(getField(raw, 'AssertRules', 'assert_rules')),
    preprocessors: asProcessorArray(getField(raw, 'PreProcessors', 'preprocessors')),
    postprocessors: asProcessorArray(getField(raw, 'PostProcessors', 'postprocessors')),
    tag: String(getField(raw, 'Tag', 'tag') ?? 'P0'),
    remark: String(getField(raw, 'Remark', 'remark') ?? ''),
  }
}

function normalizeInterfaceCase(raw: Record<string, unknown>): InterfaceYamlCase {
  return {
    case_type: 'interfaces',
    test_id: String(raw['test_id'] ?? ''),
    api_name: String(raw['api_name'] ?? ''),
    app_name: String(raw['app_name'] ?? ''),
    method: String(raw['method'] ?? 'GET'),
    url: String(raw['url'] ?? ''),
    request_head: asObject(raw['request_head']),
    request_body: asObject(raw['request_body']),
    status_code: (raw['status_code'] as string | number) ?? 200,
    assert_dict: asObject(raw['assert_dict']),
    assert_rules: asStringArray(raw['assert_rules']),
    preprocessors: asProcessorArray(raw['preprocessors']),
    postprocessors: asProcessorArray(raw['postprocessors']),
    remark: String(raw['remark'] ?? ''),
  }
}

function asObject(val: unknown): Record<string, unknown> | null {
  if (val === null || val === undefined) return null
  if (typeof val === 'object' && !Array.isArray(val)) return val as Record<string, unknown>
  return null
}

function asStringArray(val: unknown): string[] | null {
  if (val === null || val === undefined) return null
  if (Array.isArray(val)) return val.map(String) as string[]
  return null
}

function asProcessorArray(val: unknown): PreProcessorItem[] | PostProcessorItem[] | null {
  if (val === null || val === undefined) return null
  if (Array.isArray(val)) {
    return val.map(item => {
      if (typeof item === 'object' && item !== null) {
        return {
          name: String((item as Record<string, unknown>).name ?? (item as Record<string, unknown>).Name ?? ''),
          config: ((item as Record<string, unknown>).config ?? (item as Record<string, unknown>).Config ?? null) as Record<string, string> | null,
        }
      }
      return { name: String(item), config: null }
    })
  }
  return null
}

function cleanNulls(obj: Record<string, unknown>): Record<string, unknown> {
  const result: Record<string, unknown> = {}
  for (const [key, val] of Object.entries(obj)) {
    if (val === null || val === undefined) continue
    if (key.startsWith('_')) continue
    if (Array.isArray(val)) {
      result[key] = val.map(item =>
        typeof item === 'object' && item !== null ? cleanNulls(item as Record<string, unknown>) : item
      )
    } else if (typeof val === 'object' && !Array.isArray(val)) {
      result[key] = cleanNulls(val as Record<string, unknown>)
    } else {
      result[key] = val
    }
  }
  return result
}
