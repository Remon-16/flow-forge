# 共享 Schema 数据文件 / Shared Schema Data Files

本目录包含 Flow Forge 项目的公共 schema 定义，以 JSON 格式存储，作为跨语言（Python / TypeScript）的单一数据源。
This directory contains the shared schema definitions for Flow Forge, stored as JSON files, serving as the single source of truth across languages (Python / TypeScript).

## 文件说明 / File Overview

| 文件 / File | 用途 / Purpose |
|-------------|---------------|
| `columns.json` | Excel 列头定义（3组：接口定义/单用例/业务链路）/ Excel column headers (3 groups: API def, single case, biz flow) |
| `field-mapping.json` | snake_case ↔ PascalCase 字段名映射 + JSON 列标识 / Field name mapping + JSON column identifiers |
| `constants.json` | HTTP 方法 / Tag 等级 / 必填字段规则 / HTTP methods, tag levels, required field rules |
| `operators.json` | 断言规则运算符模式 / 合法函数 / 合法类型 / Assertion rule operator patterns, valid functions, valid types |
| `types.json` | 实体字段定义 — 名称/类型/描述/示例 / Entity field definitions — name/type/description/example |
| `plan_sections.json` | 测试计划章节结构（JSON Schema draft 2020-12）— 定义 business_understanding / single_api / biz_flows 三键结构，用于 AI agent 生成和 Studio 批注器渲染 / Test plan section structure (JSON Schema draft 2020-12) — defines the three-key structure used by AI agent generation and Studio annotator rendering |

## 修改规则 / Modification Rules

1. 任何 schema 变更必须先在 JSON 文件中修改，然后三个项目自动同步。
   Any schema change MUST be made in the JSON files first; all three projects will pick up the change automatically.

2. 修改 `types.json` 中字段定义后，agent 的 prompt 文件会通过 `render.py` 自动生成更新后的字段列表和示例。
   After modifying field definitions in `types.json`, agent prompt files will automatically generate updated field lists and examples via `render.py`.

3. 修改 `operators.json` 后，Python 和 TypeScript 的断言验证逻辑都需要确认兼容。
   After modifying `operators.json`, both Python and TypeScript assertion validation logic should be checked for compatibility.

## 实体类型说明 / Entity Types

| 实体 / Entity | 说明 / Description | 包含字段数 / Field Count |
|---------------|-------------------|------------------------|
| `interface_def` | API接口定义 / API interface definition | 13 |
| `single_test_case` | 单接口测试用例（继承 interface_def） / Single test case (extends interface_def) | 15 |
| `biz_step` | 业务链路步骤（继承 single_test_case，用 step_id 替换 test_id，增加 inherit） / Biz flow step (extends single_test_case) | 16 |
| `biz_flow` | 业务链路（sheet_name + steps） / Business flow (sheet_name + steps) | 2 |
| `api_summary` | API 摘要信息 / API summary | 9 |

## 使用方式 / Usage

### Python（`/python` 和 `/agent`）

```python
from flow_forge_schemas import (
    API_COLUMNS, CASE_COLUMNS, BIZ_COLUMNS,
    SNAKE_TO_PASCAL, PASCAL_TO_SNAKE,
    VALID_HTTP_METHODS, VALID_TAGS,
)

# Agent prompt 渲染
from flow_forge_schemas.render import render_field_list, render_operators_guide
```

### TypeScript（`/studio`）

```typescript
import {
    API_COLUMNS, CASE_COLUMNS, BIZ_COLUMNS,
    SNAKE_TO_PASCAL, PASCAL_TO_SNAKE,
    HTTP_METHODS, TAG_LEVELS,
} from '@flow-forge-schemas'
```
