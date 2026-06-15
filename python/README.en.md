# Flow Forge — API Automation Test Executor

**English** | [中文](README.md)

A Python 3-based HTTP API automation test executor supporting YAML/Excel-driven case management, multi-threaded concurrent execution, parameter chaining across steps, automatic login state management, and self-contained HTML report output.

## System Architecture

```mermaid
graph TD
    CLI[CLI Arguments] --> CM[Configuration Manager]
    ENV[env.yml] --> CM
    ENV_APP["env-{name}.yml"] --> CM
    CM --> |Merged Config| EXEC[Executor Factory]
    YAML[YAML Case Dir/Files] --> YP[YAML Parser]
    EXCEL[Excel Case File] --> EP[Excel Parser]
    YP --> |Single API Cases| API_EXEC[ApiTestExecutor]
    YP --> |Business Flow Cases| BIZ_EXEC[BizFlowExecutor]
    EP --> |Single API Cases| API_EXEC
    EP --> |Business Flow Cases| BIZ_EXEC
    API_EXEC --> LM[Login State Manager]
    BIZ_EXEC --> LM
    API_EXEC --> AE[Assertion Engine]
    BIZ_EXEC --> AE
    API_EXEC --> |Results| REPORT[HTML Report Generator]
    BIZ_EXEC --> |Results| REPORT
    REPORT --> HTML[Self-Contained HTML Report]
```

## Directory Structure

```
python/
├── main.py                      # CLI entry point, workflow orchestration
├── requirements.txt             # Dependencies: requests, openpyxl, pyyaml
├── env.yml                      # Base configuration (can be committed)
├── env-local.yml                # Environment-specific config (with credentials, DO NOT commit)
│
├── config/
│   ├── __init__.py
│   └── config_manager.py        # Config loading, merging, CLI override
│
├── core/
│   ├── __init__.py
│   ├── path_resolver.py         # Dot/bracket JSON path resolver
│   └── script_type.py           # Script type enum & executor registry
│
├── excel_reader/
│   ├── __init__.py
│   └── excel_parser.py          # Multi-sheet Excel parsing and validation
│
├── yaml_reader/
│   ├── __init__.py
│   └── yaml_parser.py           # YAML case file/directory parsing
│
├── executor/
│   ├── __init__.py
│   ├── base.py                  # BaseExecutor abstract base (thread pool + thread safety)
│   ├── api_test.py              # ApiTestExecutor: single API testing
│   ├── biz_flow.py              # BizFlowExecutor: multi-step business flow testing
│   └── factory.py               # Executor factory with dynamic import
│
├── auth/
│   ├── __init__.py
│   └── login_manager.py         # Thread-safe login state manager (token cache + fine-grained locks)
│
├── assertion/
│   ├── __init__.py
│   ├── engine.py                # Simple equality assertion engine (assert_dict)
│   └── rules_engine.py          # Advanced assertion rules engine (assert_rules)
│
└── reporter/
    ├── __init__.py
    ├── html_writer.py           # Self-contained HTML report generator
    └── md_writer.py             # Markdown report generator (fallback)
```

## Installation

```bash
cd python
pip install -r requirements.txt
```

### Dependencies

| Dependency | Purpose |
|------------|---------|
| `requests` | HTTP request sending |
| `openpyxl` | Excel case file reading |
| `pyyaml` | YAML configuration parsing |

## Quick Start

### 1. Configure Environment

Edit `env.yml` to set base parameters:

```yaml
scriptType: APITest
envName: local
caseFilePath: ./test_cases.xlsx
maxThread: 5
reportName: APIReport
```

Edit `env-{envName}.yml` to configure target applications and login info (see [Configuration](#configuration)).

### 2. Prepare Case Files

**Option 1: Use YAML Cases** (recommended, default agent output)

The agent-generated YAML cases are stored under the `output/` directory:

```
output/
├── single_cases/        # Single API test cases (one .yaml per case)
└── biz_flows/           # Business flow cases (one .yaml per flow)
```

You can also write YAML cases manually. See [YAML Case Format](#yaml-case-format) for the specification.

**Option 2: Use Excel Cases**

Write test cases according to the [Excel Case Format](#excel-case-format).

### 3. Run Tests

```bash
# YAML directory mode (recommended): execute all YAML cases under a directory
python main.py --yamlDir ../agent/output --envName local --apiMode all

# YAML files mode: execute specific YAML files
python main.py --yamlFiles ./case1.yaml,./case2.yaml --envName local

# Excel mode (compatible): run with default config (single API cases only)
python main.py

# Excel mode: specify environment and thread count, run all cases
python main.py --envName prod --maxThread 10 --apiMode all

# Excel mode: full parameter example
python main.py --config /path/to/env.yml --scriptType APITest --envName local \
               --caseFilePath ./test_cases.xlsx --maxThread 5 --reportName MyReport \
               --apiMode all
```

## Configuration

### Precedence

```
CLI arguments > env-{envName}.yml > env.yml > built-in defaults
```

### env.yml — Base Configuration (can be committed)

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `scriptType` | str | `APITest` | Script type (currently only `APITest`) |
| `envName` | str | Required | Environment name; loads `env-{envName}.yml` |
| `caseFilePath` | str | Required | Excel case file path (relative to main.py) |
| `maxThread` | int | `5` | Thread pool size; controls concurrency |
| `reportName` | str | `APIReport` | HTML report title |
| `apiMode` | str | `single` | Execution mode: `single` / `biz` / `all` |

### env-{envName}.yml — Environment Config (DO NOT commit, contains credentials)

Top-level dict keys correspond to "application names" matching the `AppName` column in the Excel cases.

```yaml
<AppName>:
  baseURL: http://localhost:8080        # Application base URL
  loginPath: /api/user/login            # Login endpoint path
  loginBody: userAccount,password       # Login request body field list (comma-separated)
  headTokenName: Authorization          # Header field name for the token
  resTokenPath: $.data.token            # JSON path to token in login response
  <userParamName>:                      # User config (referenced in Excel via #{})
    userAccount: admin                  # Value for loginBody fields
    password: "123456"
```

Multiple applications can be defined, each with multiple users:

```yaml
someApp:
  baseURL: http://localhost:8080
  loginPath: /api/login
  loginBody: userAccount,password
  headTokenName: Authorization
  resTokenPath: $.data.token
  adminUser:
    userAccount: user1
    password: "12345678"
  leaderUser:
    userAccount: user2
    password: "12345678"

managerURL:
  baseURL: http://localhost:8081
  loginPath: /api/manager/login
  loginBody: username,password
  headTokenName: Authorization
  resTokenPath: $.data.token
  someUser:
    username: usera1
    password: 11111*
  ...
```

### CLI Arguments

| Argument | Type | Description |
|----------|------|-------------|
| `--config` | str | Path to env.yml (default: env.yml next to main.py) |
| `--scriptType` | str | Script type, overrides env.yml |
| `--envName` | str | Environment name, overrides env.yml |
| `--caseFilePath` | str | Excel case file path, overrides env.yml |
| `--maxThread` | int | Max thread count, overrides env.yml |
| `--reportName` | str | Report name, overrides env.yml |
| `--apiMode` | str | Execution mode (`single`/`biz`/`all`), overrides env.yml |
| `--yamlDir` | str | YAML case directory path; recursively scans for all `.yaml`/`.yml` files |
| `--yamlFiles` | str | Comma-separated list of YAML case file paths |

### apiMode Values

| Value | Behavior |
|-------|----------|
| `single` | Execute only single API cases (YAML: `case_type=single`; Excel: Sheet 2) |
| `biz` | Execute only business flow cases (YAML: `case_type=biz`; Excel: Sheet 3+) |
| `all` | Execute both single API and business flow cases |

## YAML Case Format

Each test case is an independent `.yaml` file, with a `case_type` field indicating its type. YAML is the default output format of the agent and the recommended input format for the executor.

### Single API Case (case_type: single)

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

### Business Flow Case (case_type: biz)

```yaml
case_type: biz
sheet_name: User Registration & Login Flow
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
    trans: "smsCode=Step01.data.code"
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
|-------|------|-------------|
| `case_type` | str | Case type: `single` (single API) or `biz` (business flow) |
| `test_id` | str | Unique test case identifier (required for single API cases) |
| `api_name` | str | API name/description |
| `app_name` | str | Application name, matching the app key in `env-{envName}.yml` |
| `method` | str | HTTP method: `GET`/`POST`/`PUT`/`DELETE`/`PATCH` |
| `url` | str | API path (relative to app's `baseURL`), e.g., `/api/user/login` |
| `status_code` | int | Expected HTTP status code |
| `request_head` | dict | Request headers as key-value pairs |
| `request_body` | dict | Request body as key-value pairs |
| `assert_dict` | dict | Simple assertion dictionary; key = response JSON path, value = expected value |
| `assert_rules` | list[str] | Advanced assertion rules (optional); each entry is a string expression |
| `tag` | str | Tag (e.g., P0/P1/P2) |
| `remark` | str | Remarks |
| `sheet_name` | str | Business scenario name (required for business flow cases) |
| `steps` | list | List of steps (required for business flow cases) |
| `step_id` | str | Step identifier (must be unique within the same flow), e.g., `Step01` |
| `trans` | str | Inter-step data passing definition; same syntax as [Trans Field Syntax](#trans-field-syntax) |

## Excel Case Format

The Excel file contains multiple sheets structured as follows:

### Sheet 1 — API Definitions

Required columns: `TestID`, `APIName`, `AppName`, `Method`, `URL`, `StatusCode`

| Column | Type | Description |
|--------|------|-------------|
| `TestID` | str | Unique identifier; referenced by `RelevanceID` in other sheets |
| `APIName` | str | API name/description |
| `AppName` | str | Application name, matching the app key in `env-{envName}.yml` |
| `Method` | str | HTTP method: `GET`/`POST`/`PUT`/`DELETE`/`PATCH` |
| `URL` | str | API path (relative to app's `baseURL`), e.g., `/api/user/login` |
| `StatusCode` | int | Expected HTTP status code |
| `RequestHead` | JSON | Request headers, JSON string or object |
| `RequestBody` | JSON | Request body, JSON string or object |
| `AssertDict` | JSON | Assertion dictionary; key = response JSON path, value = expected value |
| `Remark` | str | Remarks |
| `Tag` | str | Tag (e.g., P0/P1/P2) |

### Sheet 2 — Single Cases

Required columns: `TestID`, `RelevanceID`

| Column | Type | Description |
|--------|------|-------------|
| `TestID` | str | Unique test case identifier |
| `RelevanceID` | str | References a `TestID` in Sheet 1; used for API reference (not enforced by executor; primarily for case generation agent indexing and querying) |
| Other columns | — | Same as Sheet 1; test case values are used directly, no merge with Sheet 1 |

### Sheet 3+ — Business Flow

Each sheet represents a business scenario; the sheet name is the scenario name. Required columns: `StepID`, `RelevanceID`

| Column | Type | Description |
|--------|------|-------------|
| `StepID` | str | Step identifier (must be unique within the same sheet), e.g., `Step01` |
| `RelevanceID` | str | References a `TestID` in Sheet 1 (not enforced by executor; primarily for case generation agent indexing and querying) |
| `Trans` | str | Inter-step data passing definition (see syntax below) |
| Other columns | — | Same as Sheet 1/Sheet 2 |

### API Definitions Notes

Sheet 1 (API Definitions) serves as reference documentation for the AI agent and is not read by the executor. Test case row values are **used directly** — they are not merged or auto-filled from API definitions. The `RelevanceID` field is for reference association, primarily used by the case generation agent for indexing and querying.

### Trans Field Syntax

`Trans` passes data between steps in a business flow:

```
variableName=sourceStepID.responseJSONPath, variableName2=sourceStepID2.responseJSONPath
```

Example:
```
username=Step01.data.username, orderId=Step02.data.orderId
```

Reference passed values in `RequestHead` or `RequestBody` using `#{variableName}`:

```json
{
  "Authorization": "#{<userParamName>}",
  "orderId": "#{orderId}"
}
```

Escape: use `\#{...}` for a literal `#{...}` — it will not be substituted.

**Trans Validation Rules:**
- No Chinese characters allowed
- Must be in `key=value` format
- Square brackets `[]` must appear in matching pairs
- `StepID` must be unique within the same sheet

### JSON Field Notes

JSON fields in Excel support the following formats:
- Standard JSON strings (double-quoted)
- Single-quoted JSON (auto-converted to double quotes)
- Chinese quotation marks `""`/`''` (auto-converted to standard double quotes)
- Direct JSON objects (already parsed to dict by openpyxl)

## Core Modules

### Configuration Manager (`config/config_manager.py`)

Singleton global configuration management:

1. Load `env.yml` for base configuration
2. Load `env-{envName}.yml`, separating top-level and application config
3. Apply CLI argument overrides
4. Provide `get()`, `get_all()`, `get_app()` interfaces

### Excel Parser (`excel_reader/excel_parser.py`)

- Reads Sheet 2 (single API) and Sheet 3+ (business flows) according to `apiMode`
- Validates `Trans` fields and deduplicates `StepID` for business flows
- Returns `parse_error` on parsing exceptions without blocking other cases

### YAML Parser (`yaml_reader/yaml_parser.py`)

- Provides two entry points: `parse_directory()` (recursive directory scan) and `parse_files()` (comma-separated file list)
- Classifies cases by the `case_type` field: `single` for single API cases, `biz` for business flow cases
- When `case_type` is missing, auto-infers: `steps` present → business flow, `test_id` present → single API
- Filters by `apiMode` (`single` returns only singles, `biz` returns only biz, `all` returns both)
- Returns the same data structure as `ExcelParser.parse()`, seamlessly integrating into the execution pipeline

### Executors

#### BaseExecutor (`executor/base.py`)

Abstract base class providing:
- `ThreadPoolExecutor` thread pool with concurrency controlled by `maxThread`
- Thread-safe result collection (`threading.Lock`)
- Unified exception handling and error result construction
- Subclasses implement `execute_single()` method

#### ApiTestExecutor (`executor/api_test.py`)

Single API test executor:
0. **URL validation**: Checks whether the URL contains the `<URL not exist>` marker (injected by the Agent during generation). If present, the case fails immediately with an error message.
1. Extracts `app_name`, `method`, `url`, `headers`, `body` from the case
2. Looks up the app's `baseURL` by `AppName`, constructs full URL
3. Calls `LoginManager` to resolve `#{userParamName}` placeholders to actual tokens
4. Sends HTTP request (GET/DELETE params in query string, POST/PUT/PATCH as JSON body, 30-second timeout)
5. Runs the assertion engine to verify the response
6. Auto-appends `status_code` assertion

#### BizFlowExecutor (`executor/biz_flow.py`)

Business flow test executor:
- Each business flow (one sheet) runs in its own thread
- Steps within a flow execute **sequentially**; any step failure aborts subsequent steps
- Before each step executes, the URL is checked for the `<URL not exist>` marker. If present, the step fails immediately.
- Uses `threading.local()` to store per-thread step response data
- `_parse_trans()` parses `key=StepID.path` mappings
- `_resolve_vars()` substitutes `#{key}` with actual response values from previous steps
- Generates an "execution chain" string (success with `→`, failure marked with `×`)

### Login State Manager (`auth/login_manager.py`)

Thread-safe token management:

```
Detect #{userParamName} → Check cache → Cache hit: return token
                                      → Cache miss → Check failure blacklist → Blacklisted: skip
                                                                               → Not blacklisted: acquire user lock
                                                                                 → POST login endpoint
                                                                                 → Success: cache token, return
                                                                                 → Failure: add to blacklist, return error
```

Key design choices:
- **Fine-grained locks**: locking at `appName:userParamName` granularity; different users can log in concurrently
- **Failure blacklist**: MD5 hash of failed login credentials to avoid repeated invalid requests
- **Token cache**: each user logs in only once; subsequent calls reuse the cached token

### Assertion Engine (`assertion/engine.py` + `rules_engine.py`)

**Simple Assertions (`assert_dict`, `engine.py`):**
- Performs field-level equality assertions on HTTP responses
- `assert_dict` keys are JSON paths (supports dot + bracket notation: `data.items[0].name`, also `$.` prefix)
- `status_code` field is special-cased, asserting against `response.status_code`
- Missing path renders as `<not found>`

**Advanced Assertions (`assert_rules`, `rules_engine.py`):**

Each rule is a string expression in the format `<left expression> <operator> [<right expression>]`.

| Operator | Description | Example |
|----------|-------------|---------|
| `==` / `!=` | Equal / Not equal | `$.data.id == 1001` |
| `>` / `>=` / `<` / `<=` | Numeric comparison | `$.data.total > 0` |
| `=~` | Regex match | `$.data.time =~ ^\\d{4}-\\d{2}-\\d{2}$` |
| `in` | Value in list | `$.data.status in ["PAID", "PENDING"]` |
| `contains` | Collection contains element | `$.data.tags contains "vip"` |
| `not_contains` | Collection does not contain element | `$.data.tags not_contains "blocked"` |
| `is_null` | Value is null | `$.data.optional is_null` |
| `is_not_null` | Value is not null | `$.data.order_id is_not_null` |
| `typeof` | Type check | `$.data.count typeof int` |

Supported functions:

| Function | Description | Example |
|----------|-------------|---------|
| `.length()` | Array length | `$.data.list.length() == 3` |
| `SUM(path)` | Sum of array elements | `SUM($.data.list[*].price)` |
| `SUM_PRODUCT(p1, p2)` | Sum of products of two fields | `SUM_PRODUCT($.data.list[*].price, $.data.list[*].count)` |

The `[*]` wildcard in paths iterates over each element of an array, used with `SUM` and `SUM_PRODUCT` functions.

### HTML Report Generator (`reporter/html_writer.py`)

Generates self-contained HTML reports (no external CSS/JS dependencies):

- **Summary section**: environment name, test time, total case count
- **Single API Cases section**: collapsible list, sorted with failures first. Each case card includes:
  - Request/response details (JSON formatted)
  - Assertion results table (field, expected, actual, pass/fail)
- **Business Flow Cases section**: one card per flow, showing the execution chain and per-step details
- Pass/fail indicated with green/red coloring
- Reports output to `python/report/` directory; filename format: `{ExcelFileName}_{timestamp}.html`

## Execution Flow

### Single API Test Flow

```mermaid
sequenceDiagram
    participant CLI
    participant Config
    participant Excel
    participant Executor
    participant LoginMgr
    participant API
    participant Assert

    CLI->>Config: Load config
    Config->>Excel: Parse case file
    Excel->>Executor: Single API case list
    loop Each case (thread pool concurrent)
        Executor->>LoginMgr: Resolve token (#{user})
        LoginMgr-->>Executor: Headers with token
        Executor->>API: Send HTTP request
        API-->>Executor: Response
        Executor->>Assert: Run assertions
        Assert-->>Executor: Assertion results
    end
    Executor->>CLI: Summary → HTML report
```

### Business Flow Test Flow

```mermaid
sequenceDiagram
    participant Thread
    participant BizFlow
    participant LoginMgr
    participant API

    Thread->>BizFlow: Execute business flow (one flow per thread)
    loop Steps execute sequentially
        BizFlow->>BizFlow: Resolve Trans variables (#{key})
        BizFlow->>LoginMgr: Resolve token
        BizFlow->>API: Send HTTP request
        API-->>BizFlow: Response
        BizFlow->>BizFlow: Store response in ThreadLocal
        BizFlow->>BizFlow: Run assertions
        alt Assertion failed
            BizFlow->>BizFlow: Abort subsequent steps, record failure
        end
    end
```

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | All cases passed |
| `1` | Some or all cases failed |
| `2` | Configuration or file parsing error (no cases executed) |
