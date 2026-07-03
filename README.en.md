# Flow Forge — API Automation Testing Framework

**English** | [中文](README.md)

![Development Status](https://img.shields.io/badge/status-Alpha-orange)
![Version](https://img.shields.io/badge/version-v0.3.0--alpha-blue)
![Branch](https://img.shields.io/badge/dev_branch-dev-brightgreen)

An AI agent-based API automation testing framework. Provide requirement documents and API documentation, and the agent automatically generates test case YAML files (with optional Excel export). Feed the cases to the CLI executor, and you get a test report. The executor integrates seamlessly with Jenkins for CI/CD pipelines.

The AI agent enables rapid test case generation, but due to potential AI hallucinations, manual review of the generated output is recommended. Test cases are stored as individual YAML files — one file per case — making them easy to review, version-control with Git, and update incrementally. Supports resumable and incremental generation — resume interrupted runs and update cases after requirement changes without regenerating everything from scratch. For detailed rules, see [agent/README.md](./agent/README.md).

## Current Status

The minimum viable pipeline has been validated end-to-end. Given a set of requirement documents, API documentation, and optional user guidance, the agent produces a test plan for manual review. Once the plan is approved, it generates single-API and business-flow test cases. If the reviewer rejects the plan and provides feedback, the agent revises the plan accordingly; the review loop can iterate until the plan is accepted, at which point test cases are produced. The underlying LLM is deepseek-v4-flash.

**Agent example** — see [agent/README.md](./agent/README.md) for details:

```bash
# Full pipeline (output defaults to ./output_<timestamp>)
python agent/main.py --requirement docs/req.md --api docs/api.yaml

# Specify output directory
python agent/main.py --requirement docs/req.md --api docs/api.yaml --output my_output

# Output YAML only (no Excel)
python agent/main.py --requirement docs/req.md --api docs/api.yaml --output-format yaml
```

The executor supports both single-threaded and multi-threaded modes (concurrent case execution, not load testing). In business-flow mode, responses from earlier steps can feed data into later steps, enabling cross-API parameter chaining. The assertion engine supports both simple equality checks and advanced multi-operator assertion rules (numeric comparisons, regex matching, list aggregation, etc.).

**Executor example** — see [python/README.md](./python/README.md) for details:

```bash
# Option 1: Use YAML cases
python main.py --config /path/to/env.yml --envName local --yamlDir ./output --apiMode all

# Option 2: Use Excel cases
python main.py --config /path/to/env.yml --scriptType APITest --envName local \
               --caseFilePath ./test_cases.xlsx --maxThread 5 --reportName MyReport \
               --apiMode all
```

A Tauri desktop application, Flow Forge Studio, has been implemented. It supports visual editing of both Excel (.xlsx) and YAML (.yaml) test case formats, featuring form-based YAML editing, right-click file operations, an advanced assertion rule editor, a JSON tree editor, font zoom (Ctrl+wheel), and an interactive Markdown plan annotator with popovers. A case format converter is also provided for bidirectional Excel ↔ YAML conversion. See [studio/README.en.md](./studio/README.en.md) for details.

## System Architecture

```mermaid
graph TD
    REQ[Requirements Doc] --> AGENT[AI Case Generation Agent]
    API[API Documentation] --> AGENT
    KB[(Grep Search)] -.-> AGENT
    AGENT --> |plan.md| REVIEW[Manual Review]
    REVIEW --> |Approved| AGENT
    AGENT --> |YAML/Excel Cases| EXEC[Test Executor]
    EXEC --> LM[Login State Manager]
    EXEC --> AE[Assertion Engine]
    EXEC --> |HTML Report| REPORT[Test Report]
    JENKINS[Jenkins CI/CD] --> |Trigger| EXEC
    EXEC --> |Exit Code| JENKINS
```

The manual review step supports two modes: (1) typing `y`/`n` with text feedback directly in the CLI; (2) typing `r` to use the [studio's Markdown Plan Annotator](./studio/README.en.md) to add structured annotations on the rendered test plan — click on annotation highlights to view, edit, or delete annotations inline via a popover — the agent then revises the plan based on the annotation file.

The framework consists of two core components:

- **[agent/](./agent/)** — AI Case Generation Agent: reads requirement documents + API documentation, passes through a two-phase pipeline of "Plan Generation → Manual Review → Case Orchestration", and outputs test case YAML files (with optional Excel export).
- **[python/](./python/)** — API Test Executor + Case Format Converter: reads YAML case directories/files or Excel case files, automatically manages login state, executes HTTP requests with multi-threading, runs assertions, and generates self-contained HTML test reports. Provides Excel ↔ YAML bidirectional conversion and YAML/Excel → standalone pytest code generation.
- **[studio/](./studio/)** — Flow Forge Studio desktop application: provides visual editing of test cases (Excel + YAML) and interactive Markdown annotation of test plans.

The two components are decoupled via **YAML files** as the primary contract (Excel remains compatible) — the agent generates a specific format, and the executor parses that format. Users are free to choose: use the agent to auto-generate cases, manually write YAML/Excel cases and run them directly with the executor, or use the Excel editor for editing.

## Project Structure

```text
flow-forge/
├── README.en.md                  # Project overview (this file)
├── agent/                        # AI Case Generation Agent
│   ├── plugins/                  # Custom case-attribute generator plugins (optional)
│   └── utils/                    # Utility modules (token_counter.py, etc.)
├── python/                       # API Test Executor + Case Format Converter
│   ├── converter/                # Excel ↔ YAML bidirectional conversion tool
│   ├── i18n/                     # Internationalization (Chinese / English)
│   └── processors/               # Pre/Post processor plugins (optional)
└── studio/                       # Flow Forge Studio desktop app (case editor, plan annotator)
```

## Workflow

### Option 1: AI Agent Generation + Executor (Full Pipeline)

```text
Requirements Doc + API Documentation
       │
       ▼
  AI Agent generates test plan (plan.md)
       │
       ▼
  Manual review & revision of test plan
       │
       ▼
  AI Agent generates YAML cases (output/ directory)
       │
       ▼
  Manual review of YAML cases (optional parameter tweaks)
       │
       ▼
  Executor runs YAML directory
       │
       ▼
  View HTML test report
```

### Option 2: Manually Written YAML/Excel + Executor

```text
Manually write YAML or Excel cases (executor format)
       │
       ▼
  Executor runs cases (--yamlDir or --caseFilePath)
       │
       ▼
  View HTML test report
```

### Option 3: AI Generates Excel → Batch Edit in Studio → Convert to YAML for Diff (Recommended)

```text
AI Agent outputs Excel format (--output-format excel or both)
       │
       ▼
  Batch review and edit in Flow Forge Studio (adjust tags, fill in parameters, modify assertions, etc.)
       │
       ▼
  Convert Excel to YAML with converter (python converter_main.py excel2yaml)
  When standalone pytest tests are needed, use yaml2pytest / excel2pytest
       │
       ▼
  Commit YAML to Git for version control; review changes file-by-file with git diff
       │
       ▼
  Executor runs the YAML directory
       │
       ▼
  View HTML test report
```

> **Why this workflow?** Excel is ideal for batch editing — in Studio you can quickly browse, sort, and modify large numbers of cases at once. YAML is ideal for diffing — one file per case means git diff shows exactly what changed in each review. Generate Excel first for editing efficiency, then convert to YAML for traceability.

## CI/CD Integration (Jenkins)

The executor is a pure CLI tool that communicates results via exit codes, allowing direct integration into Jenkins pipelines.

## Usage Recommendations

- **Document splitting**: When using weaker models with small output windows (e.g., `max_output_tokens` ≤ 4096), split requirement and API documents by module and limit each batch to about 8 interfaces to avoid truncation. Stronger models (GPT-4o, DeepSeek V4 Pro, etc.) typically have large enough output windows and don't need deliberate splitting.
- **Batch size guidelines**:
  - Strong models: skeleton batch size ~30 (`skeleton_batch_size`), plan generation no splitting (`plan_single_batch_size: -1` + `plan_biz_flow_batch_size: -1`)
  - Weak models: skeleton batch size ~5-10, single-API chunk size ~3-5 (`plan_single_batch_size`), biz flow chunk size ~1-3 (`plan_biz_flow_batch_size`)
  - Configure in `env.yaml` under the `pipeline` section.
- **Auto mode**: After tuning skills and plugins, use `--auto` to skip human review and speed up batch generation.
- **Case type selection**: Use `--case-type` or `pipeline.case_type` in `env.yaml` to generate only single-API cases (`single`) or only business flow cases (`biz`). Defaults to both (`both`).

## Anti-Hallucination & Error Handling

- **Text-Only Limitation**: The AI agent only processes text. Image/scanned content in PDFs will NOT be extracted — provide PDFs with extractable text layers or plain-text documents. Binary files (.png, .jpg) are explicitly rejected with an error.
- **LLM Output Count Validation (Anti-Hallucination)**: After skeleton generation, data filling, assertion generation, and URL correction, the number of output items is automatically validated against the input count. Mismatches trigger automatic retries. Each validation check supports a configurable strategy (fail / warn / skip) via `validation.rules` in `env.yaml`.
- **Skeleton Batching & Plan Chunking**: Skeleton generation uses batched LLM calls (default 30 test points per batch) for improved count accuracy. Test plan generation uses an "outline + four phases" approach — first generating a lightweight JSON outline, then: A) global business understanding + flowcharts → B) single-API test points grouped by `plan_single_batch_size` → C) business flow tests batched by `plan_biz_flow_batch_size` → D) assembly. Each chunk independently calls the LLM with a reset step counter. Both configs support `-1` (no splitting) for strong models.
- **Plugin Error Handling**: The agent/ plugin system supports three error strategies — `skip`, `warn`, `fail`. The `fail` strategy aborts the pipeline and enables resumption from the failed stage via checkpoints. The python/ processor system halts the current case immediately on failure and records the error in the test report.
- **LLM Thinking Mode**: Configure vendor-specific thinking/reasoning parameters (e.g., `thinking` for DeepSeek, `reasoning_effort` for OpenAI o-series) via `llm.extra_params` in `env.yaml`. Parameters are passed directly to the API as-is.

## Running Tests

```bash
# agent/ tests
cd agent && python -m pytest tests/ -v

# python/ tests
cd python && python -m pytest tests/ -v
```

## Technology Stack

| Component | Technology |
|-----------|------------|
| Case Generation Agent | Python 3, OpenAI API, prance (OpenAPI parsing), pymupdf (PDF parsing), LLM context compression |
| Test Executor | Python 3, requests, openpyxl, pyyaml |
| Configuration | YAML multi-environment config files |
| Report Output | Self-contained HTML (no external CSS/JS) |
| CI/CD | Jenkins Pipeline, CLI exit codes |

## Design Philosophy

- **YAML/Excel as Contract**: The agent and executor are decoupled through YAML/Excel files. Users can freely choose how to produce test cases.
- **Human-in-the-Loop**: AI-generated test plans require manual approval before final case generation, ensuring quality control.
- **CLI-Driven**: The executor is a pure CLI tool with no GUI dependencies, suitable for CI/CD environments.
- **Self-Contained Reports**: HTML reports embed all styles and scripts inline — open them directly in a browser without a web server.
- **Extensible Processors**: Pre/post processor extension points allow custom logic such as HMAC signing, SQL cleanup, etc.
- **Context Compression**: When processing long documents, intermediate results from chunked processing are automatically compressed into concise summaries, freeing context window space. Only accumulated results are compressed — system prompts and skill content remain untouched.

## Plugin & Processor System

The project provides a three-layer extension mechanism for custom requirements:

| Module | Extension Point | Description |
|--------|----------------|-------------|
| `python/processors/` | PreProcessor / PostProcessor | Request/response processing — modify requests, inspect responses, manage external resources |
| `agent/plugins/` | CaseAttributeGenerator | AI agent plugins — automatically fill custom attributes after case generation |
| `studio` | PreProcessors / PostProcessors fields | Edit and validate processor configs in the UI |

**Typical scenarios**:
- Add HMAC signature before requests (PreProcessor)
- Clean up test data in a database after requests (PostProcessor)
- AI agent automatically recommends processor configs for generated cases (agent plugin)

See each subdirectory's README for details: `python/README.md`, `agent/README.md`, `studio/README.md`.
