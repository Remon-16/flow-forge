# flowforge-testing — Flow Forge Skill for Strong Models

[中文](README.md) | **English**

This skill distills Flow Forge's test-case workflow into instructions loadable
by ReAct agents such as Codex, opencode, and Claude Code: multi-document
analysis → plan (optional) → YAML case generation → schema validation →
executor run → failure triage → revision/reporting.

## Why a separate skill

The `agent/` pipeline is designed for weak models (English prompts, document
chunking, context compression, human review). Having a strong model drive
that pipeline wastes tokens. This skill lets a strong model apply the same
quality bar with its own ReAct abilities, calling the `python/` executor and
converter only where determinism is required.

## Features

- **Generate mode**: requirement/API documents (multiple) + table structures
  /business rules → plan (default) → YAML cases.
- **Modify mode**: requirement/API changes + existing cases → diff analysis
  → add/change/delete → validate and execute.
- **Validation**: `ff_tool validate` performs static checks against
  `shared/schemas` (required fields, assertions, inherit, processor configs).
- **Execution & triage**: drives the `python/` executor and distinguishes
  "case error / business bug / environment issue".
- **Conversion**: YAML ↔ Excel on demand.
- **Two modes**: plan (default, approval first) / auto (unattended run).
- **Middleware**: database/Redis/MQ pre/post processing through the generic
  processor mechanism, not tied to any specific business.

## Directory Layout

```text
flowforge-testing/
├── SKILL.md                      # agent instructions (English), entry point
├── README.md / README.en.md      # this documentation
├── flowforge.config.yaml.example # config template
├── scripts/
│   ├── resolve_python.py         # resolve the Python interpreter by config
│   ├── ff_tool.py                # unified validate / execute / convert entry
│   ├── i18n/                     # log internationalization (zh_CN / en_US)
│   └── tests/                    # script tests (zero LLM calls)
└── references/
    └── PLAN_TEMPLATE.md          # plan output structure template
```

## Quick Start

```bash
# 1) Copy the config template and fill it in
cp flowforge.config.yaml.example flowforge.config.yaml
```

```yaml
# Key settings
language: zh_CN        # output language
mode: plan             # plan | auto
python:
  mode: auto           # auto | conda | venv | system
  conda_env: api_test  # e.g. api_test
```

Connect your agent to this directory (see below), then have the agent read
`SKILL.md` and start working.

## Agent Integration

### Codex

- Copy or symlink to `~/.codex/skills/flowforge-testing` (recommended, auto-discovered);
- or point to it in a session: `Use the skill at <flow-forge-repo-root>/flowforge-testing to generate test cases`.

### Claude Code

- Copy to the project's `.claude/skills/flowforge-testing/`, or point
  `--add-dir` at this directory.

### opencode

- Reference this directory's `SKILL.md` from `AGENTS.md`, or copy the
  directory into the project's `skills/` folder.

> The skill itself (SKILL.md + scripts + references) is platform-agnostic;
> only the integration method differs. Follow each platform's official docs.

## Relationship with the agent/ Weak-Model Pipeline

| Scenario | Recommended Path |
|----------|------------------|
| Strong models (GPT/Claude/DeepSeek, etc.) | this skill + a ReAct agent |
| Weak models (llama.cpp/Ollama, etc.) | the `agent/` LangGraph pipeline |
| Weak-model draft + strong-model revision | weak model drafts cases → this skill's modify mode revises them |

## Copying to Another Repository

This skill depends on the flow-forge repository layout (`python/`, `shared/`).
When copying elsewhere:

- keep `flowforge_root` in `flowforge.config.yaml` pointing at the repository
  root;
- ensure `python/` and `shared/` exist, or adjust paths in `scripts/`.

## Development & Testing

All tests run in the api_test conda environment with zero LLM calls and no
real network requests:

```bash
conda activate api_test
python -m pytest flowforge-testing/scripts/tests -v
```
