import yaml from 'js-yaml'
import { toRaw } from 'vue'
import type { YamlCase, SingleYamlCase, BizYamlCase } from '../types/yaml'

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
  }

  throw new Error(`Unknown case_type: "${caseType}". Expected "single" or "biz".`)
}

/**
 * Serialize a YamlCase object to a YAML string.
 */
export function stringifyYaml(data: YamlCase): string {
  try {
    const clean = cleanNulls(structuredClone(toRaw(data)) as unknown as Record<string, unknown>)
    return yaml.dump(clean, {
      indent: 2,
      lineWidth: -1,
      noRefs: true,
      sortKeys: false,
      flowLevel: -1,
    })
  } catch (err) {
    console.error('stringifyYaml failed:', err)
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
    remark: String(raw['remark'] ?? ''),
  }
}

function getField(raw: Record<string, unknown>, pascal: string, snake: string): unknown {
  if (pascal in raw) return raw[pascal]
  return raw[snake]
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
    StepID: String(getField(raw, 'StepID', 'step_id') ?? ''),
    RelevanceID: String(getField(raw, 'RelevanceID', 'relevance_id') ?? ''),
    Trans: String(getField(raw, 'Trans', 'trans') ?? ''),
    APIName: String(getField(raw, 'APIName', 'api_name') ?? ''),
    AppName: String(getField(raw, 'AppName', 'app_name') ?? ''),
    Method: String(getField(raw, 'Method', 'method') ?? 'GET'),
    URL: String(getField(raw, 'URL', 'url') ?? ''),
    RequestHead: asObject(getField(raw, 'RequestHead', 'request_head')),
    RequestBody: asObject(getField(raw, 'RequestBody', 'request_body')),
    StatusCode: getField(raw, 'StatusCode', 'status_code') ?? 200,
    AssertDict: asObject(getField(raw, 'AssertDict', 'assert_dict')),
    AssertRules: asStringArray(getField(raw, 'AssertRules', 'assert_rules')),
    Tag: String(getField(raw, 'Tag', 'tag') ?? 'P0'),
    Remark: String(getField(raw, 'Remark', 'remark') ?? ''),
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

function cleanNulls(obj: Record<string, unknown>): Record<string, unknown> {
  const result: Record<string, unknown> = {}
  for (const [key, val] of Object.entries(obj)) {
    if (val === null || val === undefined) continue
    if (Array.isArray(val)) {
      result[key] = val.map(item =>
        typeof item === 'object' && item !== null ? cleanNulls(item as Record<string, unknown>) : item
      )
    } else {
      result[key] = val
    }
  }
  return result
}
