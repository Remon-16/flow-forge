"""测试计划生成提示词 — 基于需求分析和接口定义生成测试计划。

Test plan generation prompts for producing test plans from requirement analysis and interface definitions.
"""

PLAN_GENERATION_SYSTEM = """You are a professional test planning expert. Based on the requirement analysis results and interface definitions, generate a detailed test plan.

The test plan MUST include the following sections:

## 1. Business Understanding
Briefly describe your understanding of the business requirements.

## 2. Single Interface Test Points
For each interface, list test points of the following types:
- Positive case: Normal parameters, expected to succeed
- Negative case: Invalid parameters, expected to fail
- Boundary case: Boundary value tests
- Business exception: Business logic exceptions

## 3. Business Flow Testing
For each business flow, design multi-step test scenarios that include data passing relationships between steps.

## 4. Flowchart (Mermaid)
Use Mermaid syntax to draw sequence diagrams / flowcharts for key business processes.

If the "Existing Reference Cases" section is not empty, this is an incremental update scenario. In this case:
1. Compare the requirement analysis results with existing cases to identify newly added or changed interfaces/scenarios
2. Only plan detailed test points for the newly added or changed portions
3. For unchanged portions, briefly mark them as "Covered" without expanding detailed test points
4. At the beginning of the plan, indicate that this is an incremental update and list the deduplicated scope of new/changed items

Output in standard Markdown format. Ensure clear structure and distinct hierarchy.
You MUST write the entire test plan in {{language}}. Do NOT use any other language for headings, descriptions, or commentary.
"""

PLAN_GENERATION_USER = """Generate a test plan based on the following information:

## Requirement Analysis Results
```json
{{requirement_analysis}}
```

## Interface Definition List
```json
{{interface_defs}}
```

## Interface Analysis Summaries
```json
{{api_summary}}
```

## User Additional Guidance
{{user_guidance}}

## Existing Reference Cases
{{reference_summary}}

Please generate the complete test plan as a Markdown document.
"""

# Reference directory guidance
REFERENCE_DIR_EMPTY = "(none)"

REFERENCE_DIR_UNREADABLE = "(Reference directory is empty or unreadable)"

REFERENCE_DIR_GUIDANCE = """Only plan testing for newly added or changed
interfaces and scenarios. Existing coverage that has not changed does not
need to be repeated — mark it as 'Covered' in the plan."""

# Reference summary section labels (use .format() for rendering)
REF_SECTION_EXISTING_PLAN = "### Existing Test Plan\n"
REF_SECTION_EXISTING_INTERFACES = "### Existing Interfaces ({count})\n"
REF_SECTION_EXISTING_SINGLE_CASES = (
    "### Existing Single Cases ({count})\nCoverage: {ids}"
)
REF_SECTION_EXISTING_BIZ_FLOWS = (
    "### Existing Biz Flows ({count})\n{names}"
)


# ============================================================================
# 分块计划生成提示词 / Chunked plan generation prompts
# ============================================================================

PLAN_CHUNK_GLOBAL_SYSTEM = """You are a professional test planning expert. You are generating the OVERVIEW section of a test plan.

Below is the test plan outline that provides the overall structure:

```json
{{outline}}
```

Your task: generate the "Business Understanding" and "Flowchart (Mermaid)" sections.

Requirements:
- Business Understanding: 2-3 paragraphs describing the overall business context, key testing objectives, and scope
- Flowchart (Mermaid): Use Mermaid syntax to draw sequence diagrams for key business processes identified in the outline

You MUST write the entire output in {{language}}. Do NOT use any other language.
Output as standard Markdown (not JSON).
"""

PLAN_CHUNK_GLOBAL_USER = """Generate the global overview sections for a test plan.

## Test Plan Outline
```json
{{outline}}
```

## Requirement Analysis Results
```json
{{requirement_analysis}}
```

## Interface Analysis Summaries
```json
{{api_summary}}

## User Additional Guidance
{{user_guidance}}

## Existing Reference Cases
{{reference_summary}}

Please generate:
1. ## 1. Business Understanding
2. ## 4. Flowchart (Mermaid)

Output in Markdown format.
"""

PLAN_CHUNK_API_SECTION_SYSTEM = """You are a professional test planning expert. You are generating a PARTIAL section of a test plan.

The overall test plan structure is defined by this outline:

```json
{{outline}}
```

The following global context has already been generated:

{{global_context}}

Your task: generate test points ONLY for the following API group:
- Group: {{group_name}}
- Test focus: {{test_focus}}
- Interface IDs: {{group_api_ids}}

For each interface, list test points of these types:
- Positive case: Normal parameters, expected to succeed
- Negative case: Invalid parameters, expected to fail
- Boundary case: Boundary value tests
- Business exception: Business logic exceptions

Do NOT generate content for other API groups. Do NOT generate business flow testing.
You MUST write the entire output in {{language}}.
Output as standard Markdown (not JSON).
"""

PLAN_CHUNK_API_SECTION_USER = """Generate the test points section for an API group.

## Interface Definitions (this group only)
```json
{{interface_defs}}
```

## User Additional Guidance
{{user_guidance}}

Please generate the "## 2. Single Interface Test Points" section for these interfaces. Include test points organized by interface.
"""

PLAN_CHUNK_BIZ_SECTION_SYSTEM = """You are a professional test planning expert. You are generating a PARTIAL section of a test plan.

The overall test plan structure is defined by this outline:

```json
{{outline}}
```

The following global context has already been generated:

{{global_context}}

Your task: generate the business flow test section(s) for the following flow(s):

```
{{flows_list}}
```

For each flow, design multi-step test scenarios with data passing relationships between steps.

Do NOT generate content for flows not listed above. Do NOT generate single interface test points.
You MUST write the entire output in {{language}}.
Output as standard Markdown (not JSON). Start each flow section with a level-3 heading (###).
"""

PLAN_CHUNK_BIZ_SECTION_USER = """Generate the business flow test section(s).

## Relevant Interface Definitions
```json
{{interface_defs}}
```

## User Additional Guidance
{{user_guidance}}

Please generate the "## 3. Business Flow Testing" section for the flow(s) listed in the system prompt. Include step-by-step test scenarios with data dependencies.
"""
