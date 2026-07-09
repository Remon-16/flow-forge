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

Convert cases into native, standalone pytest code with **zero Flow Forge dependencies** — only `pytest` + `requests` are needed. The generated code can be copied into any project and run directly, making it ideal for sharing with other teams or integrating into CI/CD.

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
    conftest.py                  # fixtures + all helper functions + standalone built-in processor implementations
    _config.py                   # environment selector (ENV = "local" → imports the corresponding _env_*.py)
    _env_local.py                # per-environment app config (parsed from env-*.yml)
    _ff_compat.py                # lightweight compat layer (PreProcessor/PostProcessor/ProcessorError stubs)
    _custom_processors/          # user-defined processors copied verbatim (import paths auto-fixed)
    test_single_cases.py         # single-API cases
    test_biz_flows.py            # business-flow cases
```

### Generated Code Features

- Request headers/body extracted as Python constants at the top of the file for easy editing and debugging
- Complete built-in assertion rule engine (multiple operators + SUM/SUM_PRODUCT/length aggregation functions)
- All built-in processors converted to standalone functions (`_apply_timestamp()`, `_apply_hmac_sign()`, etc.) with zero framework dependency
- Login/token management automatically converted to `_resolve_token()` + `_do_login()` helper functions, preserving token caching
- Custom processors bundled with near-zero modification via the `_ff_compat.py` compatibility layer

---

## Recommended Workflow

First generate Excel cases with the AI agent (`--output-format excel`), batch-edit them in [Flow Forge Studio](../../studio/README.en.md) (adjust tags, fill in parameters, modify assertions), then convert them to YAML with `excel2yaml` for Git version control — with one YAML file per case, git diff clearly shows every change, making code review straightforward. When you need to share cases or integrate into CI/CD, use `yaml2pytest` / `excel2pytest` to generate standalone pytest files.
