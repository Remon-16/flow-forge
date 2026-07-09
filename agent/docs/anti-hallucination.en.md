# Anti-Hallucination & Error Handling

[← Back to agent/README](../README.en.md)

LLMs inevitably hallucinate (inventing interfaces or URLs, producing mismatched counts, etc.). The agent has validation and correction mechanisms built into multiple stages to catch unreliable output at the generation stage as much as possible. The core principle: **correct it if you can, clearly flag it if you can't, and never let it pass silently**.

---

## Text-Only Modality Limitation

The agent only accepts text input. Image/scanned content in PDFs will not be extracted — provide PDFs with an extractable text layer or plain-text documents. Passing in binary files (such as `.png`, `.jpg`) raises an explicit error rather than silently producing empty results.

---

## LLM Output Count Validation (Anti-Hallucination)

After skeleton generation, data filling, assertion generation, and URL correction, the number of LLM output items is automatically validated against the input. On a count mismatch, it retries automatically (using `temperature > 0` to produce varied outputs).

Each validation check supports three strategy levels in `validation.rules`:

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

For the config syntax (list/dict formats) and code defaults, see the [validation section of configuration.md](./configuration.en.md#validation--case-validation).

### Skeleton Batching and Plan Chunking

- **Skeleton batching**: Skeleton generation defaults to 30 test points per batch (`skeleton_batch_size`); when test points exceed the batch size, they are automatically split into multiple batches, each calling the LLM independently and then merged, improving count accuracy at large scale.
- **Plan chunking**: The test plan uses an "outline + four-phase" approach — first a lightweight JSON outline is generated (< 1000 tokens, guaranteed not to be truncated), then generation proceeds in four phases: A) global business understanding + flowcharts → B) single-API test points grouped by `plan_single_batch_size` → C) business-flow tests merged by `plan_biz_flow_batch_size` → D) assembly. Each chunk calls the LLM independently and resets its step counter, preventing a single call from exhausting `max_steps`. Both settings support `-1` (no split); strong models can set `-1` to speed up execution.

---

## URL Correction

The interface URL is the field most prone to LLM hallucination. The agent validates whether a URL actually exists in the source document at three points:

1. **Source-level validation** (after API analysis): Compares each LLM-extracted interface URL against the source document one by one; URLs that don't match trigger LLM correction retries (up to `url_correction_max_retries` times).
2. **Skeleton-level validation** (after skeleton generation): Checks whether each URL in the skeleton exists in the source document; those that don't match are handled according to the `url_check` strategy, and LLM correction may be invoked.
3. **Final safety-net validation** (before writing YAML): A last quick string-existence check that only flags, without correcting.

### url_check Strategy and Failure Handling

`url_check` configures its strategy (`skip`/`warn`/`fail`) in `validation.rules`; when the strategy is `warn`, a `failure_action` sub-rule can be attached:

| failure_action | Behavior |
|----------------|------|
| `discard` (default) | Cases that cannot be corrected are written to `failures.yaml`, flagged, and dropped; they do not enter plugin processing |
| `keep` | Retains the skeleton, adds a URL flag prefix, and continues plugin processing |

URLs that cannot be corrected are flagged (e.g. `<URL not exist>` / `[URL_MAY_INCORRECT]`). When the executor reads a case with such a flag, it immediately marks it as failed and does not actually send an erroneous request.

> **Recommended configuration**: Set all URL correction checks to `warn`, and use `keep` to retain cases when all retries fail. Rationale: LLMs inevitably make mistakes, and even strong models have a small chance of anomalies (e.g. unstable service during a vendor's API peak hours). `warn + keep` keeps the flow from being interrupted while clearly flagging suspicious cases for human review, rather than discarding them silently.

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

- `validation.max_retries`: number of retries when count validation fails
- `url_correction_max_retries`: number of URL correction retries
- `consecutive_batch_failure_limit`: consecutive batch failure limit (`-1` = never stop)

Once a limit is reached, it is handled according to the corresponding strategy (abort / warn and continue / flag).
