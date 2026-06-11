import yaml from 'js-yaml'
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
  // Build clean output: remove null fields for cleaner YAML
  const clean = cleanNulls(structuredClone(data) as unknown as Record<string, unknown>)
  return yaml.dump(clean, {
    indent: 2,
    lineWidth: -1,
    noRefs: true,
    sortKeys: false,
    flowLevel: -1,
  })
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

function normalizeBizCase(raw: Record<string, unknown>): BizYamlCase {
  const rawSteps = Array.isArray(raw['steps']) ? raw['steps'] as Record<string, unknown>[] : []
  return {
    case_type: 'biz',
    sheet_name: String(raw['sheet_name'] ?? ''),
    steps: rawSteps.map(normalizeBizStep),
  }
}

function normalizeBizStep(raw: Record<string, unknown>): any {
  return {
    StepID: String(raw['StepID'] ?? ''),
    RelevanceID: String(raw['RelevanceID'] ?? ''),
    Trans: String(raw['Trans'] ?? ''),
    APIName: String(raw['APIName'] ?? ''),
    AppName: String(raw['AppName'] ?? ''),
    Method: String(raw['Method'] ?? 'GET'),
    URL: String(raw['URL'] ?? ''),
    RequestHead: asObject(raw['RequestHead']),
    RequestBody: asObject(raw['RequestBody']),
    StatusCode: raw['StatusCode'] ?? 200,
    AssertDict: asObject(raw['AssertDict']),
    AssertRules: asStringArray(raw['AssertRules']),
    Tag: String(raw['Tag'] ?? 'P0'),
    Remark: String(raw['Remark'] ?? ''),
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
