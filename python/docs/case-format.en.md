# Case Format

[← Back to python/README](../README.en.md)

The executor supports two case formats: **YAML** (the agent's default output, recommended) and **Excel**. The two are semantically equivalent and can be converted back and forth with the [converter](./converters.en.md).

---

## YAML Case Format

Each case is an independent `.yaml` file, with the `case_type` field distinguishing the type.

### Single-API Case (case_type: single)

```yaml
case_type: single
test_id: TC_LOGIN_001
api_name: User Login
app_name: someApp
method: POST
url: /api/user/login
request_head:
  Content-Type: application/json
request_body:
  username: admin
  password: "123456"
status_code: 200
assert_dict:
  $.code: 0
  $.msg: success
assert_rules:
  - "$.data.token is_not_null"
tag: P0
remark: Normal login verification
```

### Business-Flow Case (case_type: biz)

```yaml
case_type: biz
sheet_name: User Registration and Login Flow
steps:
  - step_id: Step01
    api_name: Send Verification Code
    app_name: someApp
    method: POST
    url: /api/sms/send
    request_body:
      phone: "13800138000"
    status_code: 200
    assert_dict:
      $.code: 0
    inherit:
      smsCode: Step01.data.code
  - step_id: Step02
    api_name: User Registration
    app_name: someApp
    method: POST
    url: /api/user/register
    request_body:
      phone: "13800138000"
      code: "#{smsCode}"
      password: "123456"
    status_code: 200
    assert_dict:
      $.code: 0
```

### YAML Field Reference

| Field | Type | Description |
|------|------|------|
| `case_type` | str | Case type: `single` (single-API) or `biz` (business-flow) |
| `test_id` | str | Unique test case identifier (required for single-API cases) |
| `api_name` | str | API name/description |
| `app_name` | str | Application name, matching the app key in `env-{envName}.yml` |
| `method` | str | HTTP method: `GET`/`POST`/`PUT`/`DELETE`/`PATCH` |
| `url` | str | API path (relative to the app's `baseURL`), e.g., `/api/user/login` |
| `status_code` | int | Expected HTTP status code |
| `request_head` | dict | Request headers, key-value object |
| `request_body` | dict | Request body, key-value object |
| `assert_dict` | dict | Simple assertion dictionary; key = response JSON path, value = expected value |
| `assert_rules` | list[str] | Advanced assertion rules list (optional); each entry is a string expression |
| `tag` | str | Tag (e.g., P0/P1/P2) |
| `remark` | str | Remarks |
| `sheet_name` | str | Business scenario name (required for business-flow cases) |
| `steps` | list | List of business-flow steps (required for business-flow cases) |
| `step_id` | str | Step identifier (must be unique within the same flow), e.g., `Step01` |
| `inherit` | dict | Inter-step data passing definition; native mapping format; syntax below |

For the complete reference of assertion operators and functions, see the assertion engine section in [Processors & Reports](./processors-and-report.en.md#assertion-engine).

---

## Excel Case Format

An Excel file contains multiple sheets:

### Sheet 1 — API Definitions

Required columns: `TestID`, `APIName`, `AppName`, `Method`, `URL`, `StatusCode`

| Column | Type | Description |
|------|------|------|
| `TestID` | str | Unique identifier; referenced by `RelevanceID` in other sheets |
| `APIName` | str | API name/description |
| `AppName` | str | Application name, matching the app key in `env-{envName}.yml` |
| `Method` | str | HTTP method |
| `URL` | str | API path (relative to `baseURL`) |
| `StatusCode` | int | Expected HTTP status code |
| `RequestHead` | JSON | Request headers, JSON string or object |
| `RequestBody` | JSON | Request body, JSON string or object |
| `AssertDict` | JSON | Assertion dictionary |
| `Remark` | str | Remarks |
| `Tag` | str | Tag |

> Sheet 1 serves only as reference documentation for the agent; **the executor does not read this sheet**. Case row values are used directly and are not merged with or auto-filled from Sheet 1. `RelevanceID` is for reference association, primarily used by the case generation agent for indexing and querying.

### Sheet 2 — Single Cases

Required columns: `TestID`, `RelevanceID`

| Column | Description |
|------|------|
| `TestID` | Unique test case identifier |
| `RelevanceID` | References a `TestID` in Sheet 1 (not enforced by the executor) |
| Other columns | Same as Sheet 1; case row values are used directly |

### Sheet 3+ — Business Flow

Each sheet represents a business scenario; the sheet name is the scenario name. Required columns: `StepID`, `RelevanceID`

| Column | Description |
|------|------|
| `StepID` | Step identifier (must be unique within the same sheet) |
| `RelevanceID` | References a `TestID` in Sheet 1 (not enforced by the executor) |
| `Inherit` | Inter-step data passing definition, JSON string format |
| Other columns | Same as Sheet 1/2 |

### Supported Formats for JSON Fields

- Standard JSON strings (double-quoted)
- Single-quoted JSON (auto-converted to double quotes)
- Chinese quotation marks `“”`/`‘’` (auto-converted to standard double quotes)
- Direct JSON objects (already parsed to dict by openpyxl)

---

## Inherit Field Syntax

`Inherit` passes data between steps of a business flow, in JSON object format (native mapping in YAML):

```yaml
# YAML format (native mapping)
inherit:
  variableName: sourceStepID.responseJSONPath
  variableName2: sourceStepID2.responseJSONPath
```

In Excel cells it is stored as a JSON string: `{"variableName": "sourceStepID.responseJSONPath"}`.

Reference passed values with `#{variableName}` in `request_head`, `request_body`, or the `url` path. URL path parameter example: `/api/users/#{userId}/orders/#{orderId}`, where the placeholders are resolved from the current step's `request_body` and substituted in place.

Escape: use `\#{...}` for a literal `#{...}` — it will not be substituted.

### Complete Example — Passing a Login Token via Inherit

```yaml
case_type: biz
sheet_name: Register, Login, and Place Order Flow
steps:
  - step_id: Step_Register
    api_name: User Registration
    app_name: someApp
    method: POST
    url: /api/user/register
    request_body:
      phone: "13800138000"
      password: "123456"
    status_code: 200
    # This step has no inherit — the response is stored automatically for later steps

  - step_id: Step_Login
    api_name: User Login
    app_name: someApp
    method: POST
    url: /api/user/login
    request_body:
      phone: "13800138000"
      password: "123456"
    status_code: 200
    inherit:
      authToken: Step_Login.data.token
      userId: Step_Login.data.id

  - step_id: Step_CreateOrder
    api_name: Create Order
    app_name: someApp
    method: POST
    url: /api/order/create
    request_head:
      Content-Type: application/json
      Authorization: "Bearer #{authToken}"   # Resolved from Inherit — skips LoginManager
    request_body:
      userId: "#{userId}"                     # Resolved from Inherit
      productId: "PROD_001"
      quantity: 1
    status_code: 200
```

In the example above, `Step_CreateOrder`'s `Authorization: "Bearer #{authToken}"` takes its token from `Step_Login`'s response rather than from LoginManager's pre-configured credentials — because `authToken` is declared in Inherit, the executor recognizes it as already provided and skips LoginManager.

### Inherit Validation Rules

- Chinese characters are not allowed
- Must be `key=value` (key-value) format
- Square brackets `[]` must appear in matching pairs
- `StepID` must be unique within the same sheet / business flow
