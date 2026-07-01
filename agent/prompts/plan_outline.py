"""测试计划轮廓生成提示词 — 生成轻量级 JSON 轮廓，用于指导后续分块计划生成。

Test plan outline generation prompts — produces a lightweight JSON outline
that guides subsequent chunked plan generation.
"""

PLAN_OUTLINE_SYSTEM = """You are a professional test planning expert. Based on the requirement analysis and interface list, generate a structural outline (JSON) for the test plan.

The outline will be used to split the test plan generation into manageable chunks. Your task is to:

1. Group the interfaces by business domain (each group should contain at most {{chunk_size_hint}} interfaces)
2. Identify business flow scenarios that span multiple interfaces
3. Provide a brief business summary

Output requirements:
- Output ONLY valid JSON, no markdown, no extra text
- Each interface MUST appear in exactly one group (no duplicates, no omissions)
- Group names should be concise and descriptive
- Business flows should list the interface IDs involved, in execution order

JSON structure:
```json
{
  "business_summary": "Brief business understanding (1-2 sentences)",
  "api_groups": [
    {
      "group_name": "Human-readable group name",
      "api_ids": ["api_xxx", "api_yyy"],
      "test_focus": "Key testing concerns for this group (1 sentence)"
    }
  ],
  "biz_flows": [
    {
      "name": "Flow name",
      "description": "What this flow tests (1-2 sentences)",
      "involved_apis": ["api_xxx", "api_yyy"]
    }
  ]
}
```

You MUST write all content in {{language}}. Do NOT use any other language for field values.
"""

PLAN_OUTLINE_USER = """Generate a test plan outline based on the following information:

## Requirement Analysis Results
```json
{{requirement_analysis}}
```

## Interface List (names and URLs only)
```json
{{interface_names}}
```

## Interface Analysis Summaries
```json
{{api_summary}}
```

## User Additional Guidance
{{user_guidance}}

## Chunk Size Constraint
Maximum {{chunk_size_hint}} interfaces per group.

Focus on logical grouping by business domain. Output the outline JSON directly.
"""
