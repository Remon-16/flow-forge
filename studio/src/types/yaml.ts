// YAML case data types — mirrors the executor YAML format

import type { PreProcessorItem, PostProcessorItem } from './excel'

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
  preprocessors: PreProcessorItem[] | null
  postprocessors: PostProcessorItem[] | null
  remark: string
}

export interface InterfaceYamlCase {
  case_type: 'interfaces'
  test_id: string
  api_name: string
  app_name: string
  method: string
  url: string
  request_head: Record<string, unknown> | null
  request_body: Record<string, unknown> | null
  status_code: number | string
  assert_dict: Record<string, unknown> | null
  assert_rules: string[] | null
  preprocessors: PreProcessorItem[] | null
  postprocessors: PostProcessorItem[] | null
  remark: string
}

export interface YamlBizStep {
  step_id: string
  relevance_id: string
  trans: Record<string, string>
  api_name: string
  app_name: string
  method: string
  url: string
  request_head: Record<string, unknown> | null
  request_body: Record<string, unknown> | null
  status_code: number | string
  assert_dict: Record<string, unknown> | null
  assert_rules: string[] | null
  preprocessors: PreProcessorItem[] | null
  postprocessors: PostProcessorItem[] | null
  tag: string
  remark: string
}

export interface BizYamlCase {
  case_type: 'biz'
  sheet_name: string
  steps: YamlBizStep[]
}

export type YamlCase = SingleYamlCase | BizYamlCase | InterfaceYamlCase

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
    preprocessors: null,
    postprocessors: null,
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
    step_id: '',
    relevance_id: '',
    trans: {},
    api_name: '',
    app_name: '',
    method: 'GET',
    url: '',
    request_head: null,
    request_body: null,
    status_code: 200,
    assert_dict: null,
    assert_rules: null,
    preprocessors: null,
    postprocessors: null,
    tag: 'P0',
    remark: '',
  }
}

export function createDefaultInterfaceCase(): InterfaceYamlCase {
  return {
    case_type: 'interfaces',
    test_id: '',
    api_name: '',
    app_name: '',
    method: 'GET',
    url: '',
    request_head: null,
    request_body: null,
    status_code: 200,
    assert_dict: null,
    assert_rules: null,
    preprocessors: null,
    postprocessors: null,
    remark: '',
  }
}
