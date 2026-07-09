# 校验规则与断言参考

[← 返回 studio/README](../README.md)

Studio 在编辑时对用例进行实时校验。本文档列出 Excel/YAML 编辑器的校验规则、处理器字段校验，以及 AssertRules 运算符与函数参考。

---

## Excel 编辑器校验规则

| 校验项 | 适用范围 | 规则 | UI 表现 |
|--------|---------|------|---------|
| RelevanceID | 单接口用例、业务链路 | 必须在接口定义页的 TestID 集合中存在 | 单元格标红 |
| StepID | 业务链路 | 同一 Sheet 内不得重复 | 单元格标红 |
| Inherit 格式 | 业务链路 | JSON 对象格式（key: StepID.path） | 单元格标红 + Tooltip |
| Inherit 括号 | 业务链路 | `[` 与 `]` 数量一致，`(` 与 `)` 数量一致 | 单元格标红 + Tooltip |
| Inherit 中文 | 业务链路 | 不允许包含中文字符 | 单元格标红 + Tooltip |
| AssertRules 格式 | 全部 | 运算符合法性、路径语法、函数名、期望值 | 行尾 ✗ 图标 + Tooltip |
| URL 存在性 | 全部 | URL 包含 `<URL not exist>` 标记（由 Agent 注入） | 输入框红色边框 + 警告图标 + Tooltip |
| JSON 格式 | JSON 字段 | 合法 JSON 字符串 | 文本区下方红色提示 |

## YAML 编辑器校验规则

| 校验项 | 适用范围 | 规则 | UI 表现 |
|--------|---------|------|---------|
| StepID | 业务链路 | 同一文件内不得重复 | 输入框标红 |
| Inherit 格式 | 业务链路 | JSON 对象格式，括号匹配，无中文 | 输入框标红 + Tooltip |
| URL 存在性 | 全部 | URL 包含 `<URL not exist>` 标记 | 输入框标红 |
| AssertRules 格式 | 全部 | 同 Excel 编辑器 | 行尾 ✗ 图标 + Tooltip |

## 处理器字段校验

PreProcessors / PostProcessors 列：

- 允许为空
- 必须为有效的 JSON 数组格式
- 每项必须有 `name` 字段（非空字符串）
- `config` 字段可选，若存在必须为对象

---

## AssertRules 运算符与函数参考

### 运算符

| 运算符 | 说明 | 示例 |
|--------|------|------|
| `==` | 等于 | `$.data.code == 0` |
| `!=` | 不等于 | `$.data.status != ERROR` |
| `>` | 大于（数值） | `$.data.price > 10.5` |
| `>=` | 大于等于（数值） | `$.data.total >= 100` |
| `<` | 小于（数值） | `$.data.age < 150` |
| `<=` | 小于等于（数值） | `$.data.size <= 1000` |
| `=~` | 正则匹配 | `$.data.time =~ ^\d{4}-\d{2}-\d{2}$` |
| `in` | 值在列表中 | `$.data.status in ["PAID","PENDING"]` |
| `contains` | 包含子串 | `$.data.tags contains "premium"` |
| `not_contains` | 不包含子串 | `$.data.error not_contains "timeout"` |
| `is_null` | 为空 | `$.data.error is_null` |
| `is_not_null` | 不为空 | `$.data.token is_not_null` |
| `typeof` | 类型检查 | `$.data.count typeof int` |

### 函数

| 函数 | 说明 | 示例 |
|------|------|------|
| `.length()` | 数组长度 | `$.data.list.length() == 3` |
| `SUM(path)` | 通配路径求和 | `SUM($.data.list[*].price)` |
| `SUM_PRODUCT(p1, p2)` | 两个通配路径逐元素乘积求和 | `SUM_PRODUCT($.data.items[*].price, $.data.items[*].qty)` |

> 该运算符与函数集合与 [python/ 执行器的断言引擎](../../python/docs/processors-and-report.md#断言引擎) 保持一致。
