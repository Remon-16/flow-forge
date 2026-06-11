// YAML case data types — mirrors the executor YAML format

export interface SingleYamlCase {
  case_type: 'single'
  test_id: string
  relevance_id: string
  tag: string
  api_name: string
  app_name: string
  method: string
  url: string
  request_head: Record<string, unknown> | null
  request_body: Record<string, unknown> | null
  status_code: number | string
  assert_dict: Record<string, unknown> | null
  assert_rules: string[] | null
  remark: string
}

export interface YamlBizStep {
  StepID: string
  RelevanceID: string
  Trans: string
  APIName: string
  AppName: string
  Method: string
  URL: string
  RequestHead: Record<string, unknown> | null
  RequestBody: Record<string, unknown> | null
  StatusCode: number | string
  AssertDict: Record<string, unknown> | null
  AssertRules: string[] | null
  Tag: string
  Remark: string
}

export interface BizYamlCase {
  case_type: 'biz'
  sheet_name: string
  steps: YamlBizStep[]
}

export type YamlCase = SingleYamlCase | BizYamlCase

// Default empty YAML cases for creating new files

export function createDefaultSingleCase(): SingleYamlCase {
  return {
    case_type: 'single',
    test_id: '',
    relevance_id: '',
    tag: 'P0',
    api_name: '',
    app_name: '',
    method: 'GET',
    url: '',
    request_head: null,
    request_body: null,
    status_code: 200,
    assert_dict: null,
    assert_rules: null,
    remark: '',
  }
}

export function createDefaultBizCase(): BizYamlCase {
  return {
    case_type: 'biz',
    sheet_name: '',
    steps: [],
  }
}

export function createDefaultBizStep(): YamlBizStep {
  return {
    StepID: '',
    RelevanceID: '',
    Trans: '',
    APIName: '',
    AppName: '',
    Method: 'GET',
    URL: '',
    RequestHead: null,
    RequestBody: null,
    StatusCode: 200,
    AssertDict: null,
    AssertRules: null,
    Tag: 'P0',
    Remark: '',
  }
}
