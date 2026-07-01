# flow_forge_schemas — Python 共享 Schema 包

本包为 `/python` 和 `/agent` 两个 Python 项目提供公共的测试用例 schema 定义。
所有常量和字段映射从 `shared/schemas/*.json` 动态加载。

## 安装 / Installation

```bash
# 从项目根目录安装（可编辑模式）
pip install -e shared/py
```

或者在代码中注入路径：

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared', 'py'))
```

## 模块 / Modules

### `flow_forge_schemas` — 常量导出

| 导出 / Export | 类型 / Type | 说明 / Description |
|---------------|------------|-------------------|
| `API_COLUMNS` | `list[str]` | 接口定义列头（13列） |
| `CASE_COLUMNS` | `list[str]` | 单接口用例列头（15列） |
| `BIZ_COLUMNS` | `list[str]` | 业务链路步骤列头（16列） |
| `SNAKE_TO_PASCAL` | `dict[str,str]` | snake_case → PascalCase 映射 |
| `PASCAL_TO_SNAKE` | `dict[str,str]` | PascalCase → snake_case 映射 |
| `JSON_FIELDS` | `frozenset[str]` | JSON 格式字段名集合 |
| `VALID_HTTP_METHODS` | `frozenset[str]` | 合法 HTTP 方法 |
| `VALID_TAGS` | `frozenset[str]` | 合法 Tag 等级 |
| `TAG_LEVELS` | `list[str]` | Tag 等级列表（含 P4） |
| `REQUIRED_SINGLE` | `list[str]` | 单接口用例必填字段 |
| `REQUIRED_BIZ_STEP` | `list[str]` | 业务链路步骤必填字段 |
| `REQUIRED_BIZ_FLOW` | `list[str]` | 业务链路必填字段 |
| `OPERATOR_LIST` | `list[dict]` | 断言运算符列表 |
| `VALID_FUNCTIONS` | `frozenset[str]` | 合法断言函数 |
| `VALID_TYPES` | `frozenset[str]` | typeof 合法类型 |

### `flow_forge_schemas.render` — Prompt 渲染工具

| 函数 / Function | 说明 / Description |
|----------------|-------------------|
| `render_field_list(entity_type, lang)` | 生成字段列表描述文本（含类型和说明） |
| `render_json_example(entity_type, pascal_case, indent)` | 生成 JSON 示例 |
| `render_operators_guide(lang)` | 生成断言运算符说明文本 |
| `render_field_constraints(entity_type, lang)` | 生成字段约束说明 |
