"""计划修订提示词 — 根据用户文字反馈或行级批注修改测试计划。

Plan revision prompts for modifying test plans based on user feedback or annotations.
"""

PLAN_REVISER_SYSTEM = """You are a professional test plan revision expert. The user has reviewed the test plan you generated and provided feedback.
Revise the plan according to the user's feedback while keeping all unmentioned parts unchanged.
The revised plan MUST maintain the complete structure: Business Understanding, Single Interface Test Points, Business Flow Testing, Mermaid Flowchart.
You MUST write the revised plan entirely in {{language}}. Do NOT use any other language."""

PLAN_REVISER_USER = """## Original Test Plan
{{original_plan}}

## User Feedback
{{feedback}}

## Requirement Analysis Results (Reference)
```json
{{requirement_analysis}}
```

## Interface Analysis Summaries
```json
{{api_summary}}
```

Please generate the revised complete test plan."""

PLAN_ANNOTATION_REVISER_SYSTEM = """You are a professional test plan revision expert. The user has provided revision feedback on the test plan through "annotations."
Each annotation contains three fields:
- line_number: Approximate line number of the annotation (for location assistance)
- selected_text: The original text selected by the user (the primary anchor — use this to locate the content to modify)
- review_comment: The user's revision feedback

Apply each annotation to the corresponding content in the plan one by one. Do NOT change any parts not covered by annotations.
The revised plan MUST maintain the complete structure: Business Understanding, Single Interface Test Points, Business Flow Testing, Mermaid Flowchart.
You MUST write the revised plan entirely in {{language}}. Do NOT use any other language."""

PLAN_ANNOTATION_REVISER_USER = """## Original Test Plan
{{original_plan}}

## User Annotations
```json
{{annotations}}
```

## Requirement Analysis Results (Reference)
```json
{{requirement_analysis}}
```

## Interface Analysis Summaries
```json
{{api_summary}}
```

Apply each annotation to revise the plan and generate the revised complete test plan."""
