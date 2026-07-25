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


# ============================================================================
# 流程关联匹配提示词 / Flow association matching prompts
# 用于 _llm_match_flows() — LLM 语义匹配孤儿场景与 Mermaid 流程图。
# Used by _llm_match_flows() — semantically match orphaned scenarios with diagrams.
# ============================================================================

# 流程关联匹配 — 系统提示词 / Flow association matching — system prompt
FLOW_MATCH_SYSTEM = """You are a flow association expert. Your task is to
semantically match business flow test scenarios with Mermaid flow diagrams.

You will receive:
1. A list of biz_flow_scenarios — each with "name" and "description" fields
2. A list of Mermaid flow diagrams — each with "name" and "diagram" fields

For each scenario, determine which Mermaid diagram it semantically matches.
Key matching criteria:
- The scenario and diagram describe the same or closely related business process
- The scenario's steps align with the diagram's flow nodes/transitions
- A single Mermaid diagram CAN match multiple scenarios (e.g. normal path +
  error path scenarios both derived from the same business flow diagram)

Return a JSON object with a single "matches" field:
```json
{
  "matches": {
    "scenario_name_1": "mermaid_diagram_name",
    "scenario_name_2": "mermaid_diagram_name",
    "scenario_name_3": null
  },
  "explanation": "Brief explanation of matching rationale"
}
```

Rules:
- If a scenario matches a diagram, map it to the EXACT diagram name from the list.
- If NO diagram matches a scenario, map it to null.
- All scenario names provided MUST appear in the "matches" object.
- Do NOT add an "unmatched_scenarios" field — the code will detect unmatched
  scenarios from null values in "matches".
"""

# 流程关联匹配 — 用户提示词 / Flow association matching — user prompt
FLOW_MATCH_USER = """## Unmatched Scenarios (code matching failed)
{scenarios_json}

## Available Mermaid Flow Diagrams
{mermaids_json}

These scenarios could not be matched by exact name. Match each one to
the most semantically appropriate Mermaid diagram. A scenario that describes
a variation of a flow (e.g. error path) may share the same diagram."""
