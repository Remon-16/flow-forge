# flow_forge_schemas — Python Shared Schema Package

This package provides shared test case schema definitions for the `/python` and `/agent` Python projects.
All constants and field mappings are dynamically loaded from `shared/schemas/*.json`.

## Installation

```bash
# Install from project root (editable mode)
pip install -e shared/py
```

Or inject the path in code:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared', 'py'))
```

## Modules

### `flow_forge_schemas` — Constants

| Export | Type | Description |
|--------|------|-------------|
| `API_COLUMNS` | `list[str]` | Interface definition columns (13 cols) |
| `CASE_COLUMNS` | `list[str]` | Single case columns (15 cols) |
| `BIZ_COLUMNS` | `list[str]` | Biz flow step columns (16 cols) |
| `SNAKE_TO_PASCAL` | `dict[str,str]` | snake_case → PascalCase mapping |
| `PASCAL_TO_SNAKE` | `dict[str,str]` | PascalCase → snake_case mapping |
| `JSON_FIELDS` | `frozenset[str]` | JSON-format field names |
| `VALID_HTTP_METHODS` | `frozenset[str]` | Valid HTTP methods |
| `VALID_TAGS` | `frozenset[str]` | Valid tag levels |
| `TAG_LEVELS` | `list[str]` | Tag level list (includes P4) |
| `REQUIRED_SINGLE` | `list[str]` | Required fields for single case |
| `REQUIRED_BIZ_STEP` | `list[str]` | Required fields for biz step |
| `REQUIRED_BIZ_FLOW` | `list[str]` | Required fields for biz flow |
| `OPERATOR_LIST` | `list[dict]` | Assertion operator list |
| `VALID_FUNCTIONS` | `frozenset[str]` | Valid assertion functions |
| `VALID_TYPES` | `frozenset[str]` | Valid types for typeof operator |

### `flow_forge_schemas.render` — Prompt Rendering

| Function | Description |
|----------|-------------|
| `render_field_list(entity_type, lang)` | Generate field list description with types |
| `render_json_example(entity_type, pascal_case, indent)` | Generate a JSON example |
| `render_operators_guide(lang)` | Generate assertion operators guide |
| `render_field_constraints(entity_type, lang)` | Generate field constraint notes |
