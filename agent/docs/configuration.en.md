# Configuration & CLI Reference

[← Back to agent/README](../README.en.md)

This document covers the agent's complete configuration options (`env.yaml`), the translation tool configuration (`translate_env.yaml`), and all command-line arguments.

---

## env.yaml — Main Configuration File

The agent uses `env.yaml` (YAML format) as its unified configuration. Create it by copying the template:

```bash
cp env.example.yaml env.yaml
# Edit env.yaml and fill in your configuration
```

`env.example.yaml` ships with full bilingual comments and is the authoritative source for configuration options. Each section is explained below.

### llm — LLM Provider Configuration

```yaml
llm:
  provider: openai        # Only openai is supported (see note below)
  api_key: sk-...         # API key (required)
  model: gpt-4o           # Model name
  temperature: 0.3        # Generation temperature 0.0~2.0
  max_output_tokens: 4096 # Max output tokens per call
  context_window: 128000  # Context window size (tokens)
  context_compression_threshold: 0.9  # Context compression threshold (0.95 for reasoning models, 0.8 for small-window models)
  base_url: ""            # API base URL; leave empty for official OpenAI, fill in for third parties
  max_concurrency: 1      # Max concurrent requests (0 = unlimited)
  rate_limit_delay: 0.0   # Minimum interval between requests, in seconds
  retry_base_delay: 2.0   # Base retry delay, in seconds
  request_timeout: 600.0  # HTTP request timeout in seconds (connect + read)
  extra_params: {}        # Extra API params (e.g. thinking mode, see below)
```

> **Only OpenAI-compatible APIs are supported**: `provider` currently only implements `openai` (`llm/factory.py` uses `langchain_openai.ChatOpenAI`). Any service that exposes an OpenAI-compatible endpoint can be connected by setting `base_url`:
> - **DeepSeek**: `base_url: "https://api.deepseek.com"`, `model: deepseek-v4-flash`
> - **Ollama (local)**: `base_url: "http://<host>:11434/v1"`, `model: qwen2.5-coder:14b-instruct-q6_K`
> - **Official OpenAI**: leave `base_url` empty

#### Thinking Mode

Configure vendor-specific thinking/reasoning parameters via `llm.extra_params`; the parameters are passed as-is to the OpenAI SDK's `chat.completions.create()` as `**kwargs`:

```yaml
# DeepSeek thinking mode
llm:
  extra_params:
    reasoning_effort: "high"
    extra_body: {"thinking": {"type": "enabled"}}

# OpenAI o-series reasoning effort
llm:
  extra_params:
    reasoning_effort: medium
```

> Parameter names and values depend on the specific model/API vendor; consult the vendor's documentation before configuring. Unsupported parameters may be ignored or raise errors.

### pipeline — Pipeline Settings

```yaml
pipeline:
  max_steps: 10                      # Max agent steps
  max_retries: 3                     # Max retries for LLM calls
  max_steps_no_progress: 5           # Max steps with no progress
  consecutive_batch_failure_limit: 3 # Consecutive batch failure limit (-1 = never stop)
  skeleton_batch_size: 30            # Skeleton generation batch size (test points per batch)
  plan_single_batch_size: 8          # Single-API test point group size (-1 = no split, -1 recommended for strong models)
  case_type: both                    # Case generation type: both | single | biz
  plugin_batch_size: 10              # Plugin processing batch size (-1 = no batching)
  auto: false                        # Auto mode: skip human review (recommended for nightly batch generation)
```

#### Case Type Selection (case_type)

| Value | Description |
|----|------|
| `both` | Generate both single-API and business-flow cases (default) |
| `single` | Generate single-API cases only; skip the business-flow stage |
| `biz` | Generate business-flow cases only; skip the single-API stage |

The skipping logic runs at the code level and does not affect outline generation — the outline still contains the complete `api_groups` and `biz_flows`. It can also be overridden with the `--case-type` CLI argument.

### knowledge — Knowledge Base

> The knowledge base is currently a Beta feature.

```yaml
knowledge:
  enabled: false     # Enable the knowledge base (grep-based plain-text search)
  dir: ./knowledge   # Knowledge base directory
```

See the [Knowledge Base section in how-it-works.md](./how-it-works.en.md#knowledge-base) for details.

### validation — Validation & Correction

```yaml
validation:
  # ··· Case format validation ···
  case_format_enabled: true            # Enable case format validation (was enabled)
  case_format_max_retries: 3           # Case format validation retry limit

  # ··· URL doc-match correction ···
  url_doc_match_rules:
    max_retries: 3                     # URL correction retry limit (was url_doc_match_max_retries)
    strategy: warn                     # Strategy after correction exhausted: fail | warn | skip

  # ··· Case generation validation rules ···
  case_gen_rules:
    - check: skeleton_count
      strategy: warn
    - check: url_check
      strategy: warn
      failure_action: keep   # url_check only: discard (send to failures.yaml) | keep (retain and continue plugin processing)
    - check: data_fill_count
      strategy: warn
    - check: assertion_count
      strategy: warn
```

**Strategy values**: `fail` (abort and retry) | `warn` (warn and continue) | `skip` (bypass).

**Both YAML forms are supported** (via `_parse_validation_rules` in `config/settings.py`):

```yaml
# List format
case_gen_rules:
  - check: url_check
    strategy: warn
    failure_action: keep

# Dict format (shorthand)
case_gen_rules:
  skeleton_count: fail
  url_check: warn

# Dict format (nested, can include failure_action)
case_gen_rules:
  url_check:
    strategy: warn
    failure_action: keep
```

> **Code defaults vs. example**: When `case_gen_rules` is not configured, the code defaults `skeleton_count` / `data_fill_count` / `assertion_count` to `fail` and `url_check` to `warn` (`settings.py`). `env.example.yaml` shows all of them as `warn` for demonstration only — the effective values come from your configuration or the code defaults.

For the detailed behavior of each validation check and URL correction, see [anti-hallucination.md](./anti-hallucination.en.md).

### output — Output Settings

```yaml
output:
  dir: ./output      # Output root directory
  format: both       # yaml | excel | both
```

### plugins / skills — Plugins and Skills

```yaml
plugins:
  enabled: true
  modules:
    - plugins.official.data_filling.DataFillingPlugin
    - plugins.official.assertion_generation.AssertionGenerationPlugin

skills:
  enabled: true
  agents:
    data_filler:
      - foli_mall_data_filling
    assertion_generator:
      - foli_mall_assertion
```

See [plugins-and-skills.md](./plugins-and-skills.en.md) for details.

### agent / logging

```yaml
agent:
  lang: zh_CN          # UI language: zh_CN | en_US

logging:
  log_to_output: false # Whether to persist logs to output_dir/logs/agent.log (off by default)
```

---

## CLI Arguments

Main entry point: `python main.py`. Full argument list (matching `cli/parser.py`):

| Argument | Description |
|------|------|
| `--requirement PATH [PATH ...]` | Requirement document path(s) (`.txt` / `.md` / `.pdf`), one or more |
| `--api PATH` | API documentation path (OpenAPI `.yaml`/`.json` or Markdown `.md`) |
| `--output PATH` | Output root directory (default `./output_<timestamp>`) |
| `--output-format {yaml,excel,both}` | Output format (default `both`; falls back to `env.yaml` when omitted) |
| `--parse-mode {raw,rule,llm}`, `-m` | API doc parse mode (default `raw`): `raw` = LLM analyzes the raw text, `rule` = rule-based parser, `llm` = LLM pre-extraction |
| `--parser-path PATH` | Custom parser `.py` path (only effective with `--parse-mode rule`) |
| `--reference-dir PATH` | Reference directory for incremental updates |
| `--prompt TEXT`, `-p` | Additional user guidance, injected into the plan and case generation prompts |
| `--resume` | Resume execution from an existing output directory |
| `--resume-overwrite` | Overwrite existing output when resuming |
| `--auto` | Auto mode: skip all human review |
| `--case-type {single,biz,both}` | Case generation type (default `both`) |
| `--plugin-batch-size N` | Overrides `pipeline.plugin_batch_size` (plugin processing batch size); defaults to `env.yaml`. Note: this is the **plugin batch**, not plan chunking |
| `--max-steps N` | Overrides `pipeline.max_steps` (max agent steps) |
| `--max-retries N` | Overrides `pipeline.max_retries` (max retries for LLM calls) |
| `--max-steps-no-progress N` | Overrides `pipeline.max_steps_no_progress` (max steps with no progress) |
| `--consecutive-batch-failure-limit N` | Overrides `pipeline.consecutive_batch_failure_limit` (consecutive batch failure limit) |
| `--skeleton-batch-size N` | Overrides `pipeline.skeleton_batch_size` (skeleton generation batch size) |
| `--plan-single-batch-size N` | Overrides `pipeline.plan_single_batch_size` (single-API test point group size) |
| `--url-doc-match-max-retries N` | Overrides `validation.url_doc_match_rules.max_retries` (URL-to-document match retry limit) |
| `--url-doc-match-strategy {fail,warn,skip}` | Overrides `validation.url_doc_match_rules.strategy` (URL correction exhaustion strategy) |
| `--case-format-max-retries N` | Overrides `validation.case_format_max_retries` (case format validation retry limit) |
| `--validation` / `--no-validation` | Enable/disable validation (overrides `validation.case_format_enabled`) |
| `--knowledge` / `--no-knowledge` | Enable/disable knowledge base (overrides `knowledge.enabled`) |
| `--plugins` / `--no-plugins` | Enable/disable plugins (overrides `plugins.enabled`) |
| `--skills` / `--no-skills` | Enable/disable skills (overrides `skills.enabled`) |
| `--lang {zh_CN,en_US}` | Overrides `agent.lang` (UI language) |
| `--debug-snapshots` | Save debug snapshots (`interfaces.json` + `extracted_texts.json`) |
| `--debug` | Enable debug logging (full LLM I/O written to the session `debug.log`) |
| `--env PATH` | Configuration file path (default `env.yaml`) |
| `-v`, `--verbose` | Enable verbose console logging |
| `--log-to-output` | Persist logs to the output directory (`{output_dir}/logs/agent.log`) |

For command examples, see the [agent/README Quick Start](../README.en.md); for auto mode and resume/checkpoint recovery, see [how-it-works.md](./how-it-works.en.md#auto-mode).

### Config Behavior on Resume

On the first run, all CLI arguments and settings are automatically saved to `{output_dir}/memory/run_config.json`. When resuming:

- **Default behavior**: The saved configuration is used as defaults (completed stages are unaffected)
- **CLI overrides**: CLI arguments provided during `--resume` override the saved config, but only apply to stages that **have not yet run**
- **Stale override warnings**: If a CLI override would affect an already-completed stage, the system emits a `[Resume] Warning` log indicating the override may have no effect

Example: if the plan has already been generated, adding `-p "new guidance"` during `--resume` will not affect the generated plan — the system will warn that the override is stale.

> Backward compatibility: For older pipelines without `run_config.json`, resume falls back to CLI arguments entirely (same behavior as before).

**Saved config scope**: `case_type`, `user_guidance` (CLI `-p`), `output_format`, `plugin_batch_size`, `auto_mode`, `parse_mode`, `output_dir`, `api_path`, `requirement_paths`, `debug_snapshots`, `parser_path`, `reference_dir`.

---

## translate_cases.py — Case Field Translation Tool

When using a weak model (such as a small-parameter local Ollama model) to generate cases, fields like `api_name` / `sheet_name` / `remark` may come out in mixed Chinese/English or entirely in English. The translation tool acts as a **safety net**, translating the fields of already-generated cases.

> **When to use**: Run the translation **immediately after case generation**, before making any manual edits, to avoid overwriting your manual adjustments.

```bash
# Translate all cases in the entire output directory
python translate_cases.py output/cases/ --target-lang zh_CN

# Translate to a specific output directory (leaves the original directory untouched)
python translate_cases.py output/cases/ -o translated_cases/

# Preview mode (writes no files, just shows which cases need translation)
python translate_cases.py output/cases/ --target-lang zh_CN --dry-run

# Disable already-translated detection (translate everything)
python translate_cases.py output/cases/ --no-detection
```

### Translation Tool Arguments

| Argument | Description |
|------|------|
| `input_dir` | Case directory path (usually the agent's `output/cases/`) |
| `--output`, `-o` | Output root directory (default `<input_dir>_translated`) |
| `--config`, `-c` | Translator config file (default `translate_env.yaml`) |
| `--target-lang` | Target language: `zh_CN` or `en_US` |
| `--batch-size` | Max cases per batch (overrides the config file) |
| `--no-detection` | Disable already-translated detection |
| `--dry-run` | Preview mode, writes no files |
| `--log-to-output` | Persist logs to the output directory |
| `-v`, `--verbose` | Verbose console logging |

### Translation Strategy

- **Scenario inference**: References fields such as the case's method and URL to infer the test scenario, producing natural translations that match the business semantics (e.g. `DELETE /api/cart` becomes "删除购物车" / "Delete Shopping Cart", rather than a word-by-word translation).
- **Field safety**: Only `api_name` / `sheet_name` / `remark` are modified; all other fields (`test_id`, `method`, URL, etc.) are strictly preserved.
- **Already-translated detection**: By default, cases already in the target language are skipped (configurable via `detection.enabled`).
- **Input priority**: When YAML files exist in the directory, YAML is translated first; Excel is only read when no YAML is present. If the input contains Excel and YAML is used for translation, an Excel copy is also exported alongside the output.

### Independent Configuration File

The translation tool uses its own `translate_env.yaml` (template: `translate_env.example.yaml`), completely independent of the main pipeline's `env.yaml`. You can configure a different LLM for translation (for example, a weak local model for the main pipeline and a strong cloud model for translation).

```bash
cp translate_env.example.yaml translate_env.yaml
# Edit it and fill in the translation-specific LLM configuration
```
