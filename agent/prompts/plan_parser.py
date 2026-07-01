# 计划解析提示词 — 从 Markdown 测试计划中提取结构化信息。
# Plan parser prompts for extracting structured data from Markdown test plans.

PLAN_PARSER_SYSTEM = """You are a professional test plan parser. Extract structured
information from Markdown test plans.

Return the result in JSON format as follows:
```json
{
  "api_definitions": [
    {
      "test_id": "api_xxx",
      "api_name": "API name",
      "app_name": "App name",
      "method": "GET",
      "url": "/api/xxx"
    }
  ],
  "single_test_points": {
    "api_xxx": [
      {"test_id": "TP_001", "description": "Test point description", "tag": "P0", "scenario_type": "positive"}
    ]
  },
  "biz_flow_scenarios": [
    {
      "name": "Business scenario name",
      "description": "Scenario description",
      "steps": ["Step01: Login", "Step02: Query"]
    }
  ]
}
"""

PLAN_PARSER_USER = "Parse the following test plan and extract structured information:\n\n{{plan_md}}"

PLAN_CHUNK_NOTICE = """[This is part {part} of the test plan. More sections
follow.]"""
# Uses Python .format(part=...), single braces
