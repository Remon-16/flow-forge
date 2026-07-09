# Flow Forge — API Test Case Generation Agent

[中文](README.md) | **English**

A multi-agent system built on a LangGraph pipeline. It reads **requirement documents** and **API documentation**, runs them through a "plan generation → human review → case orchestration" pipeline, and automatically generates YAML test cases in the executor's format (with optional Excel export).

## What It Does

- **Multi-format input**: Requirement documents support Markdown / PDF / plain text; API documentation supports OpenAPI 3.0 (JSON/YAML) / Markdown tables.
- **Two case types**: Generates single-API test cases and multi-step business-flow test cases, supporting simple equality assertions (`assert_dict`) and advanced multi-operator assertion rules (`assert_rules`).
- **Controllable human review**: After the AI generates the test plan, a human confirms it (via `y` / `n` / `r`), ensuring quality before cases are generated.
- **Anti-hallucination**: URL correction, output-count validation, and batched generation catch unreliable output at the generation stage.
- **Pluggable extensions**: Plugins (enrich case attributes) + skills (inject domain knowledge), customizable without touching code.
- **Broad LLM compatibility**: Works with any OpenAI-compatible API — a strong cloud model (such as DeepSeek) or a weak local model (such as Ollama) both work.
- **Resume/checkpoint recovery**: Case generation can resume after an interruption, and incremental updates are supported after requirement changes.

## Quick Start

```bash
cd agent
pip install -r requirements.txt

# 1) Configure the LLM: copy the template and fill in api_key / model / base_url
cp env.example.yaml env.yaml

# 2) Run the full pipeline (requirement doc + API doc)
python main.py --requirement docs/req.md --api docs/api.yaml

# 3) Review the test plan: enter y to approve / n for text feedback / r to revise from the annotation file
# 4) After approval, cases are generated automatically and written to ./output_<timestamp>/
```

The generated cases can be run directly by the [executor](../python/README.en.md), or edited visually in [Studio](../studio/README.en.md).

## Common Commands

```bash
# Specify the output directory
python main.py --requirement docs/req.md --api docs/api.yaml --output my_output

# Output YAML only (no Excel export)
python main.py --requirement docs/req.md --api docs/api.yaml --output-format yaml

# Generate single-API cases only / business-flow cases only
python main.py --requirement docs/req.md --api docs/api.yaml --case-type single
python main.py --requirement docs/req.md --api docs/api.yaml --case-type biz

# Auto mode: skip all human review (ideal for nightly batch generation after tuning)
python main.py --requirement docs/req.md --api docs/api.yaml --auto

# Resume from an existing output directory
python main.py --resume --output output_20240101_120000

# Case field translation safety-net tool (use when a weak model outputs mixed Chinese/English)
python translate_cases.py output/cases/ --target-lang zh_CN
```

See the [Configuration & CLI Reference](./docs/configuration.en.md) for the full parameter list.

## Running Tests

```bash
python -m pytest tests/ -v
```

Tests incur no LLM API costs (all LLM calls are mocked).

## Documentation Index

| Document | Contents |
|------|------|
| [Configuration & CLI Reference](./docs/configuration.en.md) | All `env.yaml` fields, `translate_env.yaml`, all CLI parameters, the translation tool |
| [How It Works](./docs/how-it-works.en.md) | The 11-step pipeline architecture, review modes y/n/r, auto mode, knowledge base, directory structure, design philosophy |
| [Plugin & Skill System](./docs/plugins-and-skills.en.md) | Plugin development and configuration, skill injection, official plugins and built-in skills |
| [Anti-Hallucination & Error Handling](./docs/anti-hallucination.en.md) | URL correction, count validation, retry strategies (warn/retry/keep) |
