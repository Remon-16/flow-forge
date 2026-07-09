# Shared Schema Data Files

This directory contains shared schema definitions for the Flow Forge project, stored as JSON files, serving as the single source of truth across languages (Python / TypeScript).

## File Overview

| File | Purpose |
|------|---------|
| `columns.json` | Excel column headers (3 groups: API definition, single case, biz flow) |
| `field-mapping.json` | snake_case ↔ PascalCase field name mapping + JSON column identifiers |
| `constants.json` | HTTP methods, tag levels, required field rules |
| `operators.json` | Assertion rule operator patterns, valid functions, valid types |
| `types.json` | Entity field definitions — name, type, description, example values |

## Modification Rules

1. Any schema change MUST be made in the JSON files first; all three projects will pick up the change automatically.
2. After modifying field definitions in `types.json`, agent prompt files will automatically generate updated field lists and examples via `render.py`.
3. After modifying `operators.json`, both Python and TypeScript assertion validation logic should be checked for compatibility.

## Entity Types

| Entity | Description | Field Count |
|--------|-------------|-------------|
| `interface_def` | API interface definition | 13 |
| `single_test_case` | Single test case (extends interface_def) | 15 |
| `biz_step` | Biz flow step (extends single_test_case, replaces test_id with step_id, adds inherit) | 16 |
| `biz_flow` | Business flow (sheet_name + steps) | 2 |
| `api_summary` | API summary information | 9 |

## Usage

### Python (`/python` and `/agent`)

```python
from flow_forge_schemas import (
    API_COLUMNS, CASE_COLUMNS, BIZ_COLUMNS,
    SNAKE_TO_PASCAL, PASCAL_TO_SNAKE,
    VALID_HTTP_METHODS, VALID_TAGS,
)

# Agent prompt rendering
from flow_forge_schemas.render import render_field_list, render_operators_guide
```

### TypeScript (`/studio`)

```typescript
import {
    API_COLUMNS, CASE_COLUMNS, BIZ_COLUMNS,
    SNAKE_TO_PASCAL, PASCAL_TO_SNAKE,
    HTTP_METHODS, TAG_LEVELS,
} from '@flow-forge-schemas'
```
