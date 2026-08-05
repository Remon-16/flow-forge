# Case Format Conversion (converter)

[← Back to python/README](../README.en.md)

The `python/converter/` subpackage provides bidirectional Excel ↔ YAML case format conversion, as well as YAML/Excel → standalone pytest code generation. The entry point is `python/converter_main.py`, with four subcommands: `excel2yaml`, `yaml2excel`, `yaml2pytest`, and `excel2pytest`.

---

## excel2yaml — Excel → YAML

```bash
python converter_main.py excel2yaml --input cases.xlsx --output ./output/
```

Reads an Excel workbook and extracts by sheet: `API Definitions` → `interfaces/`, `Single Cases` → `single_cases/`, and remaining sheets → `biz_flows/`. Each entry becomes one `.yaml` file, with JSON columns auto-parsed into objects and field names converted from PascalCase to snake_case.

| Argument | Description |
|------|------|
| `--input`, `-i` | Input `.xlsx` file path (required) |
| `--output`, `-o` | Output YAML directory (required) |
| `--verbose`, `-v` | Enable debug logging |

---

## yaml2excel — YAML → Excel

```bash
python converter_main.py yaml2excel \
  --interfaces ./cases/interfaces/ \
  --single-cases ./cases/single_cases/ \
  --biz-flows ./cases/biz_flows/ \
  --output cases.xlsx
```

All three input directories are optional — omitted directories leave the corresponding sheet blank (headers only) in the generated Excel. YAML files must follow the Flow Forge case format (with a `case_type` field, or the type is auto-inferred from the structure).

| Argument | Description |
|------|------|
| `--interfaces` | API definitions YAML directory (optional) |
| `--single-cases` | Single-API cases YAML directory (optional) |
| `--biz-flows` | Business-flow cases YAML directory (optional) |
| `--output`, `-o` | Output `.xlsx` file path (required) |
| `--verbose`, `-v` | Enable debug logging |

---

## yaml2pytest / excel2pytest — Generate Standalone pytest Code

Convert cases into native, standalone pytest code that does **not depend on the Flow Forge executor framework**. Pure-logic processors only need `pytest` + `requests`; middleware processors (Redis/MQ/RocketMQ/DB) require their third-party libraries at runtime (`redis`, `kombu`, `sqlalchemy`, `pymysql`, `jaydebeapi`, `JPype1`, etc.). The generated code can be copied into any project with those dependencies installed and run directly, making it ideal for sharing with other teams or integrating into CI/CD.

```bash
# YAML → pytest (all three directories are optional; at least one is required)
python converter_main.py yaml2pytest \
    --interfaces ./cases/interfaces/ \
    --single-cases ./cases/single_cases/ \
    --biz-flows ./cases/biz_flows/ \
    --output ./tests/generated/

# Excel → pytest (auto-detects sheet types)
python converter_main.py excel2pytest \
    --input cases.xlsx \
    --output ./tests/generated/

# Optional arguments
python converter_main.py yaml2pytest ... --config-dir .                  # directory containing env-*.yml
python converter_main.py yaml2pytest ... --processors-dir ./processors/  # custom processors directory
```

| Argument | Applies To | Description |
|------|------|------|
| `--interfaces` / `--single-cases` / `--biz-flows` | yaml2pytest | YAML input directories (optional, at least one) |
| `--input`, `-i` | excel2pytest | Input `.xlsx` file (required) |
| `--output`, `-o` | both | Output directory (required) |
| `--config-dir` | both | Directory containing `env-*.yml` (default `python/`) |
| `--processors-dir` | both | Custom processors directory |
| `--verbose`, `-v` | both | Enable debug logging |

### Generated File Structure

```
output_dir/
    conftest.py                  # fixtures + all helper functions + processor dispatch
    _config.py                   # environment selector (ENV = "local" → imports the corresponding _env_*.py)
    _env_local.py                # per-environment app config (parsed from env-*.yml)
    _ff_compat.py                # compat layer (base-class re-exports + minimal i18n + app config access)
    _processors/                 # whole python/processors copied (all builtins + base modules, imports rewritten)
    _auth/                       # login manager dependency of processors (imports rewritten)
    _resolvers/                  # path/placeholder resolver dependency (imports rewritten)
    test_single_cases.py         # single-API cases
    test_biz_flows.py            # business-flow cases
```

### Generated Code Features

- Request headers/body extracted as Python constants at the top of the file for easy editing and debugging
- Complete built-in assertion rule engine (multiple operators + SUM/SUM_PRODUCT/length aggregation functions)
- The whole `python/processors/` package (all builtins plus base modules such as `base.py`/`redis.py`/`mq.py`/`db.py`/`rocketmq.py`) and its framework dependencies (`auth/`, `resolvers/`) are bundled with rewritten imports; future built-in or user-defined processors need no converter changes
- Login/token management automatically converted to `_resolve_token()` + `_do_login()` helper functions, preserving token caching
- Custom processors are copied into the `_processors/` root and bundled with near-zero modification via the `_ff_compat.py` compatibility layer and import rewriting

---

## Recommended Workflow

The most recommended approach: **AI generate Excel → Studio batch edit → convert to YAML for git diff → executor run**.

1. Configure docs and launch the agent in [Flow Forge Studio](../../studio/README.en.md)'s "AI Case Generator" to produce Excel cases.
2. Batch-edit in Studio's Excel Editor — adjust tags, fill in parameters, modify assertions.
3. Convert to YAML with `excel2yaml` (CLI or Studio's "Case Converter") for Git version control — with one YAML file per case, git diff clearly shows every change.
4. When you need standalone tests for sharing or CI/CD, use `yaml2pytest` / `excel2pytest`.

After debugging Skills and plugins, use `--auto` mode in CLI to skip human review — ideal for overnight batch generation.
