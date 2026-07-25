# Anti-Hallucination & Error Handling

[← Back to agent/README](../README.en.md)

LLMs inevitably hallucinate (inventing interfaces or URLs, producing mismatched counts, etc.). The agent has validation and correction mechanisms built into multiple stages to catch unreliable output at the generation stage as much as possible. The core principle: **correct it if you can, clearly flag it if you can't, and never let it pass silently**.

---

## Text-Only Modality Limitation

The agent only accepts text input. Image/scanned content in PDFs will not be extracted — provide PDFs with an extractable text layer or plain-text documents. Passing in binary files (such as `.png`, `.jpg`) raises an explicit error rather than silently producing empty results.

---

## LLM Output Count Validation (Anti-Hallucination)

After skeleton generation, data filling, assertion generation, and URL correction, the number of LLM output items is automatically validated against the input. On a count mismatch, it retries automatically (using `temperature > 0` to produce varied outputs).

Each validation check supports three strategy levels in `validation.case_gen_validation.rules`:

| Strategy | Behavior |
|------|------|
| `fail` | Abort and retry |
| `warn` | Warn and continue |
| `skip` | Skip validation |

Validation checks:

| check | Meaning |
|-------|------|
| `skeleton_count` | Skeleton count validation |
| `data_fill_count` | Data fill count validation |
| `assertion_count` | Assertion generation count validation |
| `url_check` | URL existence validation (see below) |
| `flow_match` | Flow association validation (plan parsing stage, see below) |

For the config syntax (list/dict formats) and code defaults, see the [validation section of configuration.md](./configuration.en.md#validation--case-validation).

### Skeleton Batching and Plan Chunking

- **Skeleton batching**: Skeleton generation defaults to 30 test points per batch (`skeleton_batch_size`); when test points exceed the batch size, they are automatically split into multiple batches, each calling the LLM independently and then merged, improving count accuracy at large scale.
- **Plan chunking**: The test plan uses an "outline + four-phase" approach — first a lightweight JSON outline is generated (< 1000 tokens, guaranteed not to be truncated), then generation proceeds in four phases: A) global business understanding + flowcharts → B) single-API test points grouped by `plan_single_batch_size` → C) business-flow tests (`plan_biz_flow_batch_size` is a code-level reserved constant, not user-configurable) → D) assembly. Each chunk calls the LLM independently and resets its step counter, preventing a single call from exhausting `max_steps`. `plan_single_batch_size` supports `-1` (no split); strong models can set `-1` to speed up execution.

---

## URL Correction

The interface URL is the field most prone to LLM hallucination. The agent validates whether a URL actually exists in the source document at three points:

1. **Source-level validation** (after API analysis): Compares each LLM-extracted interface URL against the source document one by one; URLs that don't match trigger LLM correction retries (up to `url_doc_match_validation.max_retries` times).
2. **Skeleton-level validation** (after skeleton generation): Checks whether each URL in the skeleton exists in the source document; those that don't match are handled according to the `url_check` strategy, and LLM correction may be invoked.
3. **Final safety-net validation** (before writing YAML): A last quick string-existence check that only flags, without correcting.

### url_check Strategy and Failure Handling

`url_check` configures its strategy (`skip`/`warn`/`fail`) in `validation.case_gen_validation.rules`; when the strategy is `warn`, a `failure_action` sub-rule can be attached:

| failure_action | Behavior |
|----------------|------|
| `discard` (default) | Cases that cannot be corrected are written to `failures.yaml`, flagged, and dropped; they do not enter plugin processing |
| `keep` | Retains the skeleton, adds a URL flag prefix, and continues plugin processing |

URLs that cannot be corrected are flagged (e.g. `<URL not exist>` / `[URL_MAY_INCORRECT]`). When the executor reads a case with such a flag, it immediately marks it as failed and does not actually send an erroneous request.

> **Recommended configuration**: Set all URL correction checks to `warn`, and use `keep` to retain cases when all retries fail. Rationale: LLMs inevitably make mistakes, and even strong models have a small chance of anomalies (e.g. unstable service during a vendor's API peak hours). `warn + keep` keeps the flow from being interrupted while clearly flagging suspicious cases for human review, rather than discarding them silently.

### Flow Association Validation (flow_match)

`flow_match` is a validation check in the plan parsing stage (step 9), configured in `validation.parse_plan_validation.rules`.

**Purpose**: After plan parsing completes, the system validates whether LLM-generated business scenarios are correctly associated with the Mermaid flow diagrams extracted during the requirements analysis stage. If there are "orphaned scenarios" — scenarios that cannot be matched to any flow diagram — it indicates the LLM may have hallucinated (inventing business flows not present in the requirements).

**Processing flow (two-step)**:

1. **Step 1 — Code-based exact name matching**: Calls `match_mermaids_to_scenarios()` to match each scenario name against diagram names by exact string comparison. In most cases the LLM preserves names, making this step efficient.
2. **Step 2 — LLM semantic matching fallback**: If mismatches remain after step 1, sends the orphaned scenarios + all Mermaid diagrams to an LLM for semantic association (supports many-to-one: one Mermaid diagram can match multiple scenarios, e.g. normal path + error path sharing the same diagram). The code validates the LLM's results (checking ID existence and scenario coverage); successfully matched scenarios are excluded from subsequent retries. Retries up to `max_retries` times.
3. If mismatches persist after retries are exhausted, handles per `strategy`:
   - `fail`: Raises an exception, aborting the pipeline
   - `skip`: Bypasses the check, retaining all flows
   - `warn`: Applies `failure_action` (see below)

**failure_action** (only effective when `strategy: warn`):

| failure_action | Behavior |
|----------------|------|
| `discard` (default) | Drops orphaned scenarios that cannot be matched, removing them from the plan |
| `keep` | Retains orphaned scenarios with a warning marker for human review |

> **Recommended configuration**: Consistent with URL correction, `warn + keep` is recommended. The LLM occasionally generates legitimate scenarios that cannot be matched by the algorithm (e.g. multiple scenario variants for the same business flow); `keep` ensures valid test scenarios are not lost.

---

## Plugin Error Handling

Plugins support three error strategies (`PluginDeclaration.error_strategy`):

| Strategy | Behavior |
|------|------|
| `skip` | Skip the failed plugin and continue with subsequent processing |
| `warn` | Log a warning and continue |
| `fail` | Abort the pipeline; you can use resume/checkpoint recovery to restart from the failed stage |

See [plugins-and-skills.md](./plugins-and-skills.en.md) for details.

---

## Retry Limits for Count Correction

All automatic retries are bounded by configured limits to avoid infinite loops:

- `case_gen_validation.max_retries`: number of retries when case format validation fails (`validation` section, was `case_format_max_retries`)
- `url_doc_match_validation.max_retries`: number of URL-to-document match retries (`validation` section, was `url_doc_match_rules.max_retries`)
- `url_doc_match_validation.rules[url_check].strategy`: strategy after URL correction exhaustion (`validation` section, `fail` | `warn` | `skip`)
- `consecutive_batch_failure_limit`: consecutive batch failure limit (`-1` = never stop)

Once a limit is reached, it is handled according to the corresponding strategy (abort / warn and continue / flag).
