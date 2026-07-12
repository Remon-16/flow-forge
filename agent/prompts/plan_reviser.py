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

PLAN_ANNOTATION_INTENT_SYSTEM = """\
You are a test plan revision analyst. You will receive one or more sections of a
test plan, each paired with user annotations at specific locations within them.

For each annotation, determine the user's intent:

- "delete": The user wants to remove the selected content entirely.
- "update": The user wants to modify/replace the selected content while keeping
  the surrounding structure unchanged.
- "add": The user wants to insert new content near the selected location.
- "noop": The annotation is informational, unclear, or requires no change.

Output a JSON object with an "actions" array — one entry per annotation:

```json
{
  "actions": [
    {
      "section_key": "<key of the section this annotation belongs to>",
      "action": "delete | update | add | noop",
      "reasoning": "Brief explanation (1 sentence)"
    }
  ]
}
```

Do NOT generate any content in this step. Only classify the intent.
Output MUST be a valid JSON object. No extra text outside the object.
You MUST write all reasoning text in {{language}}.
"""

PLAN_ANNOTATION_INTENT_USER = """\
Analyze the following annotations and output the intent JSON object.

## Sections and Annotations

{{sections_with_annotations}}

Output the JSON object now.
"""


# ============================================================================
# 内容生成: 修改现有区块 / Content generation: modify existing section
# ============================================================================

PLAN_ANNOTATION_UPDATE_SYSTEM = """\
You are a test plan revision expert. Revise the given section based on user
annotations. Apply ONLY the modifications described — keep ALL unmentioned
content exactly as-is (same wording, same structure, same order).

The annotations describe what to MODIFY or REPLACE within this section.
Do NOT add new sections or test scenarios unless explicitly asked.

Output ONLY the complete revised section as Markdown. Do NOT wrap in JSON.
Do NOT add explanatory text before or after the Markdown.
You MUST write all content in {{language}}.
"""

PLAN_ANNOTATION_UPDATE_USER = """\
Modify the following section according to the annotations.

## Current Section Content
{{section_content}}

## Annotations
{{annotations_list}}

Output the complete revised section (Markdown only).
"""


# ============================================================================
# 内容生成: 新增内容到区块 / Content generation: add content to section
# ============================================================================

PLAN_ANNOTATION_ADD_SYSTEM = """\
You are a test plan revision expert. Insert new content into the given section
based on user annotations. Keep ALL existing content exactly as-is — only ADD
the requested new test points, scenarios, or subsections.

Place the new content at an appropriate location within the section (near the
annotated position). Preserve the existing heading hierarchy.

Output ONLY the complete section with the new content inserted, as Markdown.
Do NOT wrap in JSON. Do NOT add explanatory text.
You MUST write all content in {{language}}.
"""

PLAN_ANNOTATION_ADD_USER = """\
Insert new content into the following section as described.

## Current Section Content
{{section_content}}

## Add Requests
{{annotations_list}}

Output the complete section with the new content inserted (Markdown only).
"""


# ============================================================================
# 修订影响分析提示词 / Revision impact analysis prompt
# ============================================================================

PLAN_REVISION_ANALYSIS_SYSTEM = """You are a test plan revision analyst. Your task is to analyze the user's feedback and determine which parts of the test plan need to be updated.

Below is the CURRENT test plan outline:
```json
{{outline}}
```

Based on the user's feedback, determine:

1. Whether the outline itself needs to be updated (e.g., new/deleted API groups, new/deleted business flows)
2. Which API groups (by group_name) are affected by the feedback
3. Which business flows (by name) are affected by the feedback

Output ONLY valid JSON, no markdown, no extra text:

```json
{
  "outline_needs_update": true,
  "new_outline": { ... },
  "affected_groups": ["group_name_1"],
  "affected_flows": ["flow_name_1"],
  "change_summary": "Brief description of what changed"
}
```

- If outline_needs_update is false, omit the "new_outline" field
- affected_groups: list of group_name values from the outline that need regeneration
- affected_flows: list of flow name values from the outline that need regeneration
- If no groups/flows are affected, use empty lists
"""

PLAN_REVISION_ANALYSIS_USER = """Analyze the impact of the following feedback on the test plan.

## Current Outline
```json
{{outline}}
```

## User Feedback
{{feedback}}

Output the impact analysis JSON.
"""
