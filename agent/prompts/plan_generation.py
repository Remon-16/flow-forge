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
