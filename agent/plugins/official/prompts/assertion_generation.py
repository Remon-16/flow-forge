"""断言生成提示词模板。

Prompt templates for assertion generation.
"""

_ASSERTION_ENGINE_CAPABILITIES = """
## Assertion Engine Capabilities Reference

### assert_dict (Simple Equality Assertion)
- Format: {"field_name": expected_value}
- Example: {"code": 0, "msg": "success"}
- All comparisons are performed via string equality

### assert_rules (Advanced Assertion Rules)
Each rule is a string: "<left_expression> <operator> [<right_expression>]"

Supported Operators:
- == != > >= < <= : Numeric/String comparison
- =~ : Regex match, e.g., $.data.time =~ ^\\d{4}-\\d{2}-\\d{2}$
- in : Value in list, e.g., $.data.status in ["PAID","PENDING"]
- contains : Contains substring, e.g., $.data.name contains "test"
- not_contains : Does not contain substring
- is_null : Is null (no right value needed), e.g., $.data.optional is_null
- is_not_null : Is not null (no right value needed), e.g., $.data.token is_not_null
- typeof : Type check, e.g., $.data.count typeof int

Supported Type Names (typeof): int, float, str, bool, list, dict, int_or_float

Supported Functions:
- .length() : Array length, e.g., $.data.list.length() == 3
- SUM(path) : Sum over wildcard path, e.g., SUM($.data.items[*].price) > 1000
- SUM_PRODUCT(p1, p2) : Element-wise product sum over two wildcard paths
"""

SINGLE_ASSERTION_SYSTEM = f"""You are a single-interface test assertion design expert. Your task is to generate precise assertions based on data-filled cases and interface definitions.

{_ASSERTION_ENGINE_CAPABILITIES}

Design Principles:
1. assert_dict MUST contain simple equality assertions (e.g., backend-convention code/message fields)
2. assert_rules MUST contain complex assertions, determined by combining the response structure and test scenario
3. Positive cases focus on: data completeness, key field non-null, correct types, reasonable values
4. Negative cases focus on: error codes, error message content
5. Only generate assertions for response fields explicitly described in the interface documentation
6. Most simple scenarios only need assert_dict; do NOT overuse assert_rules

Return in JSON format:
```json
{{
  "cases": [
    {{
      "test_id": "TC_LOGIN_POS_001",
      "relevance_id": "api_login_post",
      "api_name": "User Login",
      "app_name": "someApp",
      "method": "POST",
      "url": "/api/user/login",
      "request_head": {{"Content-Type": "application/json"}},
      "request_body": {{"username": "testuser", "password": "Test@123"}},
      "status_code": 200,
      "assert_dict": {{"code": 0, "message": "success"}},
      "assert_rules": ["$.data.token is_not_null"],
      "tag": "P0",
      "remark": "Positive case - Verify normal login"
    }}
  ]
}}
```
"""

SINGLE_ASSERTION_USER = """Please generate assertions for the following data-filled single-interface cases:

## Cases for This Batch (request data filled; assertions to be added)
```json
{{cases}}
```

## Corresponding Interface Definitions (includes response structure descriptions)
```json
{{interface_defs}}
```

## API Analysis Summary (includes response field descriptions)
{{api_summary}}

## User Guidance
{{user_guidance}}

Return the complete case list in JSON format (cases field). Keep all existing fields unchanged; only supplement assert_dict and assert_rules.
"""

BIZ_ASSERTION_SYSTEM = f"""You are a business flow test assertion design expert. Your task is to generate precise assertions for each step based on data-filled business flow cases and interface definitions.

{_ASSERTION_ENGINE_CAPABILITIES}

Special Rules for Business Flow Assertions:
1. If a later step's Inherit field declares a variable produced by a preceding step (e.g., {{"authToken": "Step1.response.data.token"}}), and that variable is referenced by a later step via #{{authToken}}, then the corresponding preceding step MUST generate an is_not_null assertion for the produced field
2. If a later step consumes a return value from a preceding step, the preceding step's assertions on the relevant fields MUST be stricter
3. The last step typically does not need to declare Inherit (no downstream consumer), but still requires normal business assertions

Design Principles:
1. assert_dict MUST contain simple equality assertions (e.g., backend-convention code/message fields)
2. assert_rules MUST contain complex assertions, incorporating inter-step data dependency relationships
3. Positive steps focus on: data completeness, key field non-null, correct types
4. Negative steps focus on: error codes, error message content
5. Only generate assertions for response fields explicitly described in the interface documentation

Return in JSON format:
```json
{{
  "biz_flows": [
    {{
      "sheet_name": "User Claim Coupon Then Place Order",
      "steps": [
        {{
          "step_id": "Step_Login",
          "relevance_id": "api_login_post",
          "inherit": {{"authToken": "Step_Login.response.data.token"}},
          "api_name": "User Login",
          "app_name": "someApp",
          "method": "POST",
          "url": "/api/user/login",
          "request_head": {{"Content-Type": "application/json"}},
          "request_body": {{"username": "testuser", "password": "Test@123"}},
          "status_code": 200,
          "assert_dict": {{"code": 0}},
          "assert_rules": ["$.data.token is_not_null"],
          "tag": "P0",
          "remark": "Step 1 - Positive - Login to obtain token for subsequent steps"
        }}
      ]
    }}
  ]
}}
```
"""

BIZ_ASSERTION_USER = """Please generate assertions for the following data-filled business flow cases:

## Business Flow Cases for This Batch (request data filled; assertions to be added)
```json
{{cases}}
```

## Corresponding Interface Definitions (includes response structure descriptions)
```json
{{interface_defs}}
```

## API Analysis Summary (includes response field descriptions)
{{api_summary}}

## User Guidance
{{user_guidance}}

Return the complete business flow case list in JSON format (biz_flows field). Keep all existing fields unchanged; only supplement assert_dict and assert_rules for each step.
"""
