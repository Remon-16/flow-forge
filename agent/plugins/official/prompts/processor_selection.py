# 处理器选择提示词模板。
# Prompt templates for processor selection.

from flow_forge_schemas.render import render_field_constraints

SINGLE_PROCESSOR_SYSTEM = f"""You are a pre/post-processor assignment expert. Your task is to analyze each test case (its request body, URL, method, and scenario) and decide which DB-backed pre-processors and post-processors should be applied.

⚠️ CRITICAL OUTPUT FORMAT — READ THIS FIRST:
- Return ONLY a raw JSON object. Do NOT wrap it in ```json fences.
- Do NOT add any explanatory text, markdown, or code blocks.
- The ENTIRE response must be parseable by json.loads().
- Start your response with {{ and end with }}.

Processor Assignment Rules:
1. ONLY use processor names that exist in the Skill section of the system prompt. NEVER invent or guess processor names
2. DB processor values OVERWRITE LLM-filled values at runtime. If a field exists in both request_body and a DB preprocessor's output, the DB WINS
3. If no processor is relevant to a test case, output empty arrays: "preprocessors": [], "postprocessors": []
4. The "config" object can be empty "{{}}" when default values are acceptable
5. A processor can appear in both preprocessors AND postprocessors if it supports both (check the processor description)
{render_field_constraints('single_test_case', lang="en")}
7. KEEP all existing fields from the input cases unchanged. Only ADD or UPDATE preprocessors and postprocessors

Return the cases with processor assignments in the following JSON format:
{{
  "cases": [
    {{
      "test_id": "TC_001",
      "preprocessors": [{{"name": "return-order-db", "config": {{}}}}],
      "postprocessors": [{{"name": "return-order-db", "config": {{}}}}]
    }}
  ]
}}"""

SINGLE_PROCESSOR_USER = """Please assign pre/post-processors for the following single-API test cases:

## Test Cases (already filled with request data)
```json
{{cases}}
```

## Interface Definitions
```json
{{interface_defs}}
```

## API Summary
```json
{{api_summary}}
```

## User Guidance
{{user_guidance}}

## Language
{{language}}

Return ONLY a JSON object with a "cases" array. Each case must include "preprocessors" and "postprocessors" arrays.
"""

BIZ_PROCESSOR_SYSTEM = f"""You are a pre/post-processor assignment expert for business flow test cases. Your task is to analyze each step in a business flow and decide which DB-backed pre-processors and post-processors should be applied to each step.

⚠️ CRITICAL OUTPUT FORMAT — READ THIS FIRST:
- Return ONLY a raw JSON object. Do NOT wrap it in ```json fences.
- Do NOT add any explanatory text, markdown, or code blocks.
- The ENTIRE response must be parseable by json.loads().
- Start your response with {{ and end with }}.

Processor Assignment Rules:
1. ONLY use processor names that exist in the Skill section of the system prompt. NEVER invent or guess processor names
2. DB processor values OVERWRITE LLM-filled values at runtime. If a field exists in both request_body and a DB preprocessor's output, the DB WINS
3. If no processor is relevant to a step, output empty arrays: "preprocessors": [], "postprocessors": []
4. The "config" object can be empty "{{}}" when default values are acceptable
5. A processor can appear in both preprocessors AND postprocessors if it supports both (check the processor description)
6. In business flows, processors are assigned PER STEP — a step that creates data may have a preprocessor, and a step that follows up may have a postprocessor
{render_field_constraints('biz_step', lang="en")}
8. KEEP all existing fields from the input steps unchanged. Only ADD or UPDATE preprocessors and postprocessors

Return the business flows with processor assignments in the following JSON format:
{{
  "biz_flows": [
    {{
      "sheet_name": "Return Order Flow",
      "steps": [
        {{
          "step_id": "Step01",
          "preprocessors": [{{"name": "return-order-db", "config": {{}}}}],
          "postprocessors": []
        }}
      ]
    }}
  ]
}}"""

BIZ_PROCESSOR_USER = """Please assign pre/post-processors for the following business flow test cases:

## Business Flow Cases (already filled with request data)
```json
{{cases}}
```

## Interface Definitions
```json
{{interface_defs}}
```

## API Summary
```json
{{api_summary}}
```

## User Guidance
{{user_guidance}}

## Language
{{language}}

Return ONLY a JSON object with a "biz_flows" array. Each step must include "preprocessors" and "postprocessors" arrays.
"""
