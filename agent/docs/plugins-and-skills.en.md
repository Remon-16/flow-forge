# Plugin & Skill System

[← Back to agent/README](../README.en.md)

The agent uses **plugins** to enrich case attributes after the case skeleton is generated, and **skills** to inject domain knowledge and business rules into each agent. Both are pluggable and require no changes to the framework code.

---

## Plugin System

Plugins run after the case skeleton is generated, enriching the skeleton with attributes such as request data and assertions. All plugins are configured via the `plugins` section of `env.yaml`:

```yaml
plugins:
  enabled: true          # Global switch: when false, no plugins are loaded
  modules:               # Executed in declaration order
    - plugins.official.data_filling.DataFillingPlugin
    - plugins.official.processor_plugin.ProcessorPlugin
    - plugins.official.assertion_generation.AssertionGenerationPlugin
```

### Official Plugins

| Plugin | Purpose | Scope |
|------|------|----------|
| `data_filling` | Fills request data into case skeletons (`request_head`, `request_body`, `status_code`, `tag`) | Single-API + business flow |
| `processor_selection` | Assigns DB pre/post-processors to filled cases (`preprocessors`, `postprocessors`) | Single-API + business flow |
| `assertion_generation` | Generates assertions for filled cases (`assert_dict`, `assert_rules`) | Single-API + business flow |

> **Processor priority**: DB processors (pre-processors) OVERWRITE LLM-filled field values at runtime. If `request_body.order_id` is set by both the LLM and a DB preprocessor, the DB processor's value wins.

Remove unwanted plugins from `plugins.modules`, or replace them with custom implementations.

### Enabling / Disabling

- **Global disable**: `plugins.enabled: false` → skips all plugins and generates skeletons only.
- **Fine-grained control**: add or remove module paths in the `plugins.modules` list.

### Writing a Custom Plugin

1. Subclass the `CaseAttributeGenerator` base class (`plugins/base.py`)
2. Declare a `PluginDeclaration` (plugin name, target attributes, applicable scope, etc.)
3. Implement the `generate()` method (receives a batch of cases and returns the list of cases with attributes added)

```python
from plugins.base import CaseAttributeGenerator, PluginDeclaration

class CustomPlugin(CaseAttributeGenerator):
    @property
    def declaration(self):
        return PluginDeclaration(
            plugin_name="my-custom-plugin",
            attributes=["preprocessors"],
            applies_to_single=True,
            applies_to_biz=False,
            max_retries=1,
            error_strategy="skip",
        )

    def generate(self, cases, interfaces, api_summary, api_doc_text):
        for case in cases:
            case["preprocessors"] = [...]
        return cases
```

Then add the plugin path to `plugins.modules` in `env.yaml`.

### PluginDeclaration Fields

| Field | Type | Description |
|------|------|------|
| `plugin_name` | str | Plugin name |
| `attributes` | List[str] | List of attribute names to add |
| `applies_to_single` | bool | Whether it applies to single-API cases |
| `applies_to_biz` | bool | Whether it applies to business-flow cases |
| `max_retries` | int | Number of retries per batch on failure |
| `error_strategy` | str | Total-failure strategy: `skip` / `warn` / `fail` |

When `error_strategy` is `fail`, a total plugin failure aborts the pipeline; you can use resume/checkpoint recovery to restart from the failed stage.

---

## Skill System

A skill is an add-on configuration attached to a plugin, stored as a YAML file. Via the `prompt_extension` field it appends domain knowledge or business rules to an agent's system prompt, **customizing agent behavior without modifying code**. When disabled, plugins still run normally — they just do not load the extra prompt text provided by the skill.

### Configuration

```yaml
skills:
  enabled: true       # Global switch: false turns off all skill injection
  agents:             # Assign skill files per target agent (without the .yaml extension)
    # Plugin agents
    data_filler:
      - foli_mall_data_filling
    assertion_generator:
      - foli_mall_assertion
    # Main pipeline agents (uncomment as needed)
    # case_generator:
    #   - boundary_test
```

### Injectable Agents

Skills can be injected into **all** agents (including main pipeline agents and plugin-internal agents):

- **Main pipeline agents**: `requirement_analyzer`, `api_analyzer`, `plan_generator`, `plan_parser`, `case_generator`, `skeleton_generator`; skills are stored in `skills/builtin/`.
- **Plugin agents**: `data_filler`, `processor_selector`, `assertion_generator`; skills are stored in `plugins/official/skills/`.

### Built-in Skills

| Skill file | Location | Purpose |
|-----------|------|------|
| `boundary_test.yaml` | `skills/builtin/` | Injects boundary-value testing hints into `case_generator` |
| `foli_mall_data_filling.yaml` | `plugins/official/skills/` | Data filling rules for the Foli Mall project |
| `db_processors.yaml` | `plugins/official/skills/` | Available DB pre/post-processor list (users can extend via template) |
| `foli_mall_assertion.yaml` | `plugins/official/skills/` | Assertion rules for the Foli Mall project |

### Enabling / Disabling

Skill injection uses two-layer control:

- **Global disable**: `skills.enabled: false` → all skill injection stops; plugins still run normally.
- **Fine-grained control**: edit `skills.agents` to comment out or remove unwanted agent or skill entries.

### Usage Recommendations

Encode the business rules of the project under test into skills, for example:

- HTTP status code conventions for the APIs (returning 200 vs 201 on success)
- Authentication method (JWT Token, API Key, Session Cookie)
- Baseline login credentials and test-data field formats

Once skills and plugins are tuned, you can combine them with the `--auto` auto mode for unattended batch generation (see [how-it-works.md](./how-it-works.en.md#auto-mode)).
