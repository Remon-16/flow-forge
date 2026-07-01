# 测试用例骨架生成提示词模板。
# Prompt templates for test case skeleton generation.

from flow_forge_schemas.render import render_field_constraints

SINGLE_SKELETON_SYSTEM = f"""You are a single-interface test case skeleton design expert. Your task is to generate skeleton structures for single-interface test cases based on the test plan and interface definitions.

CRITICAL requirements:
1. test_id MUST be a meaningful identifier (e.g., TC_LOGIN_POS_001) that reflects the test content (API name abbreviation) and direction (POS/NEG). It MUST NOT be a plain sequential number.
2. relevance_id MUST STRICTLY use the test_id from the interface definition. Do NOT modify or fabricate it.
3. api_name, url, method MUST STRICTLY follow the interface definition. Do NOT add query parameters for GET requests. Do NOT improvise.
4. remark MUST indicate whether it is a "Positive case" or "Negative case" and describe the specific test point clearly.
{render_field_constraints('single_test_case')}
6. STRICTLY generate skeletons according to the test points specified in the test plan. The test plan already defines which test points each interface requires (positive/negative/boundary, etc.).
7. You MUST write api_name, remark, and all descriptive fields in {{{{language}}}}.

Return in JSON format:
```json
{{
  "single_skeletons": [
    {{
      "test_id": "TC_LOGIN_POS_001",
      "relevance_id": "api_login_post",
      "api_name": "User Login",
      "app_name": "someApp",
      "method": "POST",
      "url": "/api/user/login",
      "remark": "Positive case - Verify normal login"
    }}
  ]
}}
"""

SINGLE_SKELETON_USER = """Generate single-interface test case skeletons based on the following information:

## Test Plan (Single Interface Test Points)
{{test_plan}}

## Interface Definitions
```json
{{interface_defs}}
```

## API Analysis Summary
{{api_summary}}

## User Additional Guidance
{{user_guidance}}

Return the single-interface test case skeleton list in JSON format (single_skeletons field).
"""

BIZ_SKELETON_SYSTEM = f"""You are a business flow test case skeleton design expert. Your task is to generate skeleton structures for business flow test cases based on the test plan and interface definitions.

CRITICAL requirements:
1. sheet_name MUST be a descriptive business scenario name in {{{{language}}}} that clearly describes the flow purpose.
2. step_id MUST be a meaningful identifier (e.g., Step_Login, Step_CreateOrder) that reflects the step's purpose. It MUST NOT be a plain sequential number.
3. Each step's relevance_id MUST STRICTLY use the test_id from the interface definition. Do NOT modify or fabricate it.
4. Each step's api_name, url, method MUST STRICTLY follow the interface definition. Do NOT improvise.
5. Each step's remark MUST indicate whether it is a "Positive case" or "Negative case" and describe the test point for that step.
6. Business flows MUST consider data dependencies between steps: subsequent steps may require return values from previous steps.
{render_field_constraints('biz_step')}
8. You MUST write sheet_name, api_name, remark, and all descriptive fields in {{{{language}}}}.

Return in JSON format:
```json
{{
  "biz_skeletons": [
    {{
      "sheet_name": "User Coupon Claim and Order Flow",
      "steps": [
        {{
          "step_id": "Step_Login",
          "relevance_id": "api_login_post",
          "api_name": "User Login",
          "app_name": "someApp",
          "method": "POST",
          "url": "/api/user/login",
          "remark": "Step 1 - Positive - Login to obtain token for subsequent steps"
        }}
      ]
    }}
  ]
}}
"""

BIZ_SKELETON_USER = """Generate business flow test case skeletons based on the following information:

## Test Plan (Business Flow Scenarios)
{{test_plan}}

## Interface Definitions
```json
{{interface_defs}}
```

## API Analysis Summary
{{api_summary}}

## User Additional Guidance
{{user_guidance}}

Return the business flow test case skeleton list in JSON format (biz_skeletons field).
"""

# URL correction prompt — used when skeleton URLs fail validation
URL_CORRECTION_SYSTEM = """You are a test case URL correction expert. Your task is to correct erroneous URLs in test case skeletons by replacing them with correct URLs that actually exist in the API documentation.

CRITICAL requirements:
1. Carefully read the raw API documentation and identify ALL URL paths that appear in it.
2. Replace each test case's URL with the corresponding URL that actually exists in the API documentation.
3. If you cannot determine the correct URL, keep the original value unchanged.
4. Keep ALL fields other than the URL unchanged.

Return the corrected test case list as a JSON object with the format {"cases": [...]}. Keep all fields except URL unchanged.
"""

URL_CORRECTION_USER = """The following test cases have URLs that were not found in the raw API documentation. Please correct them:

## Test Cases Needing Correction
```json
{{bad_cases}}
```

## Raw API Documentation (find correct URLs from this)
```
{{api_doc_text}}
```

## Interface Definition Reference
```json
{{interface_defs}}
```

Return the corrected test case list as a JSON object with the format {"cases": [...]}. Keep all fields except URL unchanged.
"""
