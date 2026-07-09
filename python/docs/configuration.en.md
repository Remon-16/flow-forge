# Configuration & CLI Reference

[← Back to python/README](../README.en.md)

This document covers the executor's installation dependencies, configuration files (`env.yml` + `env-{envName}.yml`), CLI arguments, and execution modes.

---

## Installation

```bash
cd python
pip install -r requirements.txt
```

### Dependencies

| Dependency | Purpose |
|------|------|
| `requests` | Sending HTTP requests |
| `openpyxl` | Reading Excel case files |
| `pyyaml` | Parsing YAML configuration files |
| `pytest` | Running the built-in test suite (`tests/`); not required to run cases themselves |

---

## Configuration Precedence

```
CLI arguments > env-{envName}.yml > env.yml > built-in defaults
```

## env.yml — Base Configuration (can be committed)

| Setting | Type | Default | Description |
|--------|------|--------|------|
| `scriptType` | str | `APITest` | Script type (currently only `APITest`) |
| `envName` | str | Required | Environment name; loads the corresponding `env-{envName}.yml` |
| `caseFilePath` | str | Required | Excel case file path (relative paths are resolved against main.py) |
| `maxThread` | int | `5` | Thread pool size; controls concurrency |
| `reportName` | str | `APIReport` | HTML report title |
| `apiMode` | str | `single` | Execution mode: `single` / `biz` / `all` |
| `lang` | str | `zh_CN` | UI language: `zh_CN` / `en_US` |
| `excel_font` | str | `微软雅黑` | Font name for Excel export |

> **Scope of `excel_font`**: only the Python converter's Excel writer (`converter/excel_writer.py`) reads this setting. Studio's Excel export font is hard-coded (`微软雅黑`) and is not affected by this option.

Required settings: `envName` and `caseFilePath` (missing values terminate with exit code 2).

## env-{envName}.yml — Environment Configuration (do not commit; contains credentials)

Top-level dict keys are the "application names", corresponding to the `app_name` / `AppName` values in cases.

```yaml
<AppName>:
  baseURL: http://localhost:8080        # Application base URL
  loginPath: /api/user/login            # Login endpoint path
  loginBody: userAccount,password       # Login request body field list (comma-separated)
  headTokenName: Authorization          # Header field name for the token
  resTokenPath: $.data.token            # JSON path to the token in the login response
  <userParamName>:                      # User config (referenced in cases via #{})
    userAccount: admin                  # Values for the loginBody fields
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
```

### processor_configs — Processor Sensitive Data

Sensitive information such as database connections and secrets should not be written into cases. Declare it in the `processor_configs` section of the configuration file, and it is passed automatically to the processor's `global_config` parameter at runtime:

```yaml
processor_configs:
  hmac-sign:
    secret_env: SIGN_SECRET
    algorithm: sha256
  sql-cleanup:
    host: localhost
    port: 3306
    database: testdb
```

For details, see [Processors & Reports](./processors-and-report.en.md#pre-processors--post-processors).

---

## CLI Arguments

Main entry point `python main.py` (matching main.py's argparse):

| Argument | Type | Description |
|------|------|------|
| `--config` | str | Path to `env.yml` (default: `env.yml` in the same directory as main.py) |
| `--scriptType` | str | Script type, overrides env.yml |
| `--envName` | str | Environment name, overrides env.yml |
| `--caseFilePath` | str | Excel case file path, overrides env.yml |
| `--maxThread` | int | Max thread count, overrides env.yml |
| `--reportName` | str | Report name, overrides env.yml |
| `--apiMode` | str | Execution mode (`single`/`biz`/`all`), overrides env.yml |
| `--yamlDir` | str | YAML case directory path; recursively scans for all `.yaml`/`.yml` files under it |
| `--yamlFiles` | str | Comma-separated list of YAML case file paths |
| `--verbose`, `-v` | flag | Enable debug logging |

### apiMode Values

| Value | Behavior |
|----|------|
| `single` | Execute only single-API cases (YAML: `case_type=single`; Excel: Sheet 2) |
| `biz` | Execute only business-flow cases (YAML: `case_type=biz`; Excel: Sheet 3+) |
| `all` | Execute both single-API and business-flow cases |

For command examples, see [python/README.md Quick Start](../README.en.md).

---

## Exit Codes

| Exit Code | Meaning |
|--------|------|
| `0` | All cases passed |
| `1` | Some or all cases failed |
| `2` | Configuration or file parsing error (no cases executed) |
