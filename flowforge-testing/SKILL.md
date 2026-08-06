---
name: flowforge-testing
description: |-
  Generate, modify, validate, execute and triage Flow Forge API test cases.
  Use when the user wants to turn requirement documents, API documents,
  table structures or business rules into executable YAML/Excel test cases,
  revise existing cases after requirement/API changes, run cases with the
  Flow Forge executor and diagnose failures, or convert cases between YAML
  and Excel. Expects the flow-forge repository layout (python/, shared/).
---

# Flow Forge Test Case Generation & Execution

## 1. Preflight

1. Locate the flow-forge repository root: prefer `flowforge_root` from
   `flowforge.config.yaml`; otherwise use the parent directory of this skill.
   Verify the `python/` and `shared/` layout exists.
2. Load `flowforge.config.yaml`. If it does not exist, copy it from
   `flowforge.config.yaml.example` and ask the user for the key settings
   (`language`, Python environment, executor defaults).
3. Resolve the Python interpreter by running `scripts/resolve_python.py`.
   Resolution order: `python_path` (explicit) -> configured mode
   (`conda`/`venv`/`system`) -> automatic detection. The chosen interpreter
   must be able to import `requests`, `openpyxl` and `yaml`.
4. If dependencies are missing, ask the user to install them in the
   configured environment (for example
   `conda activate api_test && pip install -r python/requirements.txt`).
   Never install packages into the conda base environment.
5. Check the executor configuration (`python/env.yml` and
   `python/env-{envName}.yml`). Fill in missing app `baseURL`, login
   settings and `processor_configs` entries from the user's deployment
   notes or documentation. If credentials are still missing, ask the user
   once for them; never guess or fabricate credentials.
6. Prepare middleware when needed: run `python/tools/h2/init_h2.py` for H2;
   start the system-under-test or middleware services as background
   subprocesses and record their PIDs so the main flow never blocks. If a
   service cannot be started automatically, report it to the user.

## 2. Inputs

- Requirement documents: `.md` / `.txt` / `.pdf`, one or more. Analyze each
  document separately, then merge and deduplicate by content
  (business flows, roles, constraints, exceptions).
- API documents: OpenAPI 3.0 (`JSON`/`YAML`) or Markdown tables, one or
  more. Merge and deduplicate interfaces by `(path, method)`.
- Optional supplementary inputs: table structures/DDL, business rules,
  existing test cases, middleware connection information, deployment
  notes. Use them during requirement analysis and case generation; do not
  output them as separate artifacts.

## 3. Work Modes

Choose the mode from the user's explicit intent:

- `plan` (default, interactive): produce a test plan for user approval
  before generating any cases.
- `auto` (when the user explicitly asks, or `mode: auto` is configured;
  for example "run it overnight" or "just run it"): skip plan display and
  confirmation and go straight to analyze -> generate -> validate ->
  execute -> report. Collect blocking issues (such as missing credentials)
  and report them once at the end instead of interrupting mid-run.
- `modify`: see Section 8.

If the user does not state a preference, default to `plan` mode and
mention that `auto` mode is available.

## 4. Plan Mode Unified Structure

Follow `references/PLAN_TEMPLATE.md` and produce five parts in the
configured language (the last one is optional but recommended):

### 4.1 Business Understanding

Business background, test scope, key business flows, user roles and test
objectives in 2-3 paragraphs.

### 4.2 Interface Summary

Start with a one-line summary: total interface count, how many require
login, and how many business-domain groups. Then present one table per
business domain, one row per interface, with columns: `URL path`, `method`,
`description`, `login required`, `auth type`, `request parameter summary`,
`response summary`, and `uncertainties/missing info` (leave blank or write
"none" when there is none). Keep parameter summaries compact
(`name: type (required?)`) instead of pasting full JSON.

### 4.3 Single API Test Points

Group interfaces by business domain (for example authentication, orders,
payments). For each interface list test points of these types: normal,
invalid parameters, boundary values and business exceptions. Annotate
middleware dependencies per point (for example "needs Redis cache
pre-seeded" or "needs a completed order created in the database").

### 4.4 Business Flow Scenarios

Each flow must span at least 2 interfaces. For every flow provide: scenario
description, step order, data-passing relationships between steps,
required middleware pre/post processing per step, and one Mermaid sequence
diagram.

### 4.5 Test Execution Plan (light constraints, optional)

Environment, execution scope and priorities in one or two lines. Do not
over-constrain the format.

Present the plan to the user, accept feedback (add/remove scenarios, adjust
priorities, correct understanding), and iterate until the user approves.
Do not generate cases before approval. The `plan.md` workspace artifact
follows the same structure in both `plan` and `auto` modes.

## 5. Case Generation

- Output workspace layout (mirrors the executor's expectations):

  ```text
  <workspace>/
  ├── plan.md
  ├── cases/
  │   ├── interfaces/*.yaml      # reference only, skipped by the executor
  │   ├── single_cases/*.yaml
  │   └── biz_flows/*.yaml
  └── report/
  ```

- Default output is YAML only; convert to Excel only when the user asks
  (via `scripts/ff_tool.py convert yaml2excel`).
- Schema authority: `shared/schemas/types.json`, `constants.json` and
  `operators.json` (loaded through `shared/py/flow_forge_schemas`) are the
  single source of truth. Markdown docs such as `python/docs/case-format.md`
  are explanatory only; on conflict the schema wins. Mention doc/schema
  drift in the final report when noticed.
- Single API cases: fields per schema (`test_id`, `relevance_id`,
  `api_name`, `app_name`, `method`, `url`, `request_head`, `request_body`,
  `status_code`, `assert_dict`, `assert_rules`, `tag`, `remark`).
- Business flow cases: `sheet_name` + `steps`; `step_id` must be unique
  within a flow; pass data between steps with `inherit`
  (`variable -> sourceStepID.response.json.path`) and reference values via
  `#{variable}` in request body/headers/URL; `inherit` keys and values must
  not contain Chinese characters.
- Assertions: use `assert_dict` for equality checks and `assert_rules` with
  operators/functions from `operators.json` (for example `=~`, `in`,
  `contains`, `typeof`, `.length()`, `SUM`), following the explanations in
  `python/docs/processors-and-report.md`.
- Middleware pre/post processing:
  1. Identify required preconditions, cache presets, message verifications,
     signatures or timestamps from requirements, table structures and
     business rules.
  2. Reuse processors already available in the target environment: the
     usable catalog is whatever actually loads there (check
     `python/processors/` and the configuration). The built-in
     `order-fixture`/`cart-fixture`/`return-fixture`/`balance-fixture`
     plugins are foli-mall demo fixtures; treat them as examples only and
     do not assume them for the user's project.
  3. If no suitable processor exists, propose a custom processor design
     (subclass `PreProcessor`/`PostProcessor`, state the interface and
     config keys) and implement it only after the user agrees.
  4. Cases declare only `preprocessors`/`postprocessors`
     (`name` + `config`). Database/Redis/MQ connection strings and other
     sensitive values go into `processor_configs` in
     `env-{envName}.yml`, never into case files.
- User-facing text (`api_name`, `sheet_name`, `remark`, and so on) follows
  the configured language; technical fields (`test_id`, `method`, `url`)
  stay stable regardless of language.

### Executor-specific gotchas (learned from real runs)

- Business flows run one thread per flow, concurrently with each other.
  Flows sharing the same user (cart/order state) will interfere; give each
  flow its own user, or clear the cart as the first step.
- `inherit` is declared per step: every step that uses a variable must carry
  its own `inherit` mapping pointing at the producing step.
- For URL path placeholders, declare the variable in `inherit` and do NOT
  put a same-named key with a `#{...}` placeholder in `request_body` — the
  executor would inject the raw placeholder into the URL, leaving a literal
  `#` that is dropped as a URL fragment (HTTP 500 on the backend).
- Snowflake IDs exceed 2^53, so avoid exact numeric equality assertions on
  them (the rule engine compares as floats and loses precision); assert on
  string/quantity fields instead, or use `is_not_null`.
- Newly registered users start with zero balance; design order flows around
  seeded users or use recharge/balance fixtures where available.

## 6. Validation

Run `scripts/ff_tool.py validate --yamlDir <workspace>/cases` after every
generation or modification:

- required fields, field types, HTTP method, `tag` (P0-P3) and
  `status_code` range;
- `assert_dict` / `assert_rules` formats and operator validity;
- `inherit` references point to existing `step_id`s;
- referenced `preprocessors`/`postprocessors` have matching
  `processor_configs` entries in the environment config (warnings only for
  missing entries, never blocking).

Fix all validation errors before executing. `ff_tool.py validate` is the
authoritative compliance check.

## 7. Execution & Triage

Run `scripts/ff_tool.py execute --yamlDir <workspace>/cases --envName <name>
--apiMode <single|biz|all>` (extra executor args are passed through). The
subprocess runs with a configurable timeout so the flow never hangs. Exit
code semantics: `0` all passed, `1` some failed, `2` configuration or parse
error.

Classify failures as follows:

- Schema/parse errors (exit code 2 or validation failures): the case is
  wrong; fix the case.
- Assertion mismatch: read the actual response and decide whether the case
  expectation is wrong (fix the case) or the business implementation
  deviates from requirements/docs (report the business bug to the user
  with request/response evidence; never weaken or bypass the assertion).
- Environment/middleware issues (connection failures, missing config,
  services not started): fix the environment config, start services in the
  background and rerun; if it cannot be automated, report to the user with
  evidence.

After execution, report: HTML report path, pass/fail statistics, the list
of discovered business bugs, and remaining blockers.

## 8. Modify Mode

When the user provides new requirement/API documents and an existing case
directory:

1. Diff the analysis: identify added, changed and removed interfaces and
   scenarios.
2. Add/change/delete cases only for the changed parts; mark unchanged parts
   as `Covered` and note this in the summary.
3. Validate and execute after modification; on failures follow Section 7.
4. Output a change summary (which cases changed, why, and the execution
   result).

## 9. Constraints & Red Lines

- Never fabricate URLs, test data or credentials; ask the user or extract
  from user-provided documents.
- Report business bugs honestly; never hide them or bypass them in cases.
- Never install packages into the conda base environment; do not modify
  existing `agent/` or `python/` code without the user's permission.
- Start long-running services as background subprocesses and record PIDs;
  never block waiting on them.
- New scripts/code follow repository conventions: bilingual comments
  (Chinese first, English after) and internationalized log messages.

## 10. Reference Documents

Load only what the current task needs; do not load everything up front.

| Document | Purpose |
|----------|---------|
| `shared/schemas/types.json`, `constants.json`, `operators.json` | authoritative case schema |
| `python/docs/case-format.md` | case format explanation (schema wins on conflict) |
| `python/docs/processors-and-report.md` | processors, assertion engine, report details |
| `python/docs/configuration.md` | `env.yml` / `env-{envName}.yml` reference |
| `python/docs/converters.md` | Excel <-> YAML conversion reference |
| `references/PLAN_TEMPLATE.md` | plan output template |
