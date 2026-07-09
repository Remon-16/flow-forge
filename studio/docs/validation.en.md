# Validation Rules & Assertion Reference

[← Back to studio/README](../README.en.md)

Studio validates cases in real time while editing. This document lists the validation rules of the Excel/YAML editors, processor field validation, and the AssertRules operator and function reference.

---

## Excel Editor Validation Rules

| Check | Applies To | Rule | UI Indicator |
|--------|---------|------|---------|
| RelevanceID | Single-API cases, business flows | Must exist in the API definition sheet's TestID set | Cell highlighted red |
| StepID | Business flows | Must not be duplicated within the same sheet | Cell highlighted red |
| Inherit format | Business flows | JSON object format (key: StepID.path) | Cell highlighted red + tooltip |
| Inherit brackets | Business flows | `[` and `]` counts match; `(` and `)` counts match | Cell highlighted red + tooltip |
| Inherit Chinese | Business flows | Chinese characters are not allowed | Cell highlighted red + tooltip |
| AssertRules format | All | Operator validity, path syntax, function names, expected values | End-of-line ✗ icon + tooltip |
| URL existence | All | URL contains the `<URL not exist>` marker (injected by the Agent) | Red input border + warning icon + tooltip |
| JSON format | JSON fields | Valid JSON string | Red hint below the text area |

## YAML Editor Validation Rules

| Check | Applies To | Rule | UI Indicator |
|--------|---------|------|---------|
| StepID | Business flows | Must not be duplicated within the same file | Input highlighted red |
| Inherit format | Business flows | JSON object format, bracket matching, no Chinese | Input highlighted red + tooltip |
| URL existence | All | URL contains the `<URL not exist>` marker | Input highlighted red |
| AssertRules format | All | Same as the Excel editor | End-of-line ✗ icon + tooltip |

## Processor Field Validation

The PreProcessors / PostProcessors columns:

- May be empty
- Must be a valid JSON array
- Each item must have a `name` field (a non-empty string)
- The `config` field is optional; if present, it must be an object

---

## AssertRules Operators and Functions

### Operators

| Operator | Description | Example |
|--------|------|------|
| `==` | Equal to | `$.data.code == 0` |
| `!=` | Not equal to | `$.data.status != ERROR` |
| `>` | Greater than (numeric) | `$.data.price > 10.5` |
| `>=` | Greater than or equal to (numeric) | `$.data.total >= 100` |
| `<` | Less than (numeric) | `$.data.age < 150` |
| `<=` | Less than or equal to (numeric) | `$.data.size <= 1000` |
| `=~` | Regex match | `$.data.time =~ ^\d{4}-\d{2}-\d{2}$` |
| `in` | Value is in list | `$.data.status in ["PAID","PENDING"]` |
| `contains` | Contains substring | `$.data.tags contains "premium"` |
| `not_contains` | Does not contain substring | `$.data.error not_contains "timeout"` |
| `is_null` | Is empty | `$.data.error is_null` |
| `is_not_null` | Is not empty | `$.data.token is_not_null` |
| `typeof` | Type check | `$.data.count typeof int` |

### Functions

| Function | Description | Example |
|------|------|------|
| `.length()` | Array length | `$.data.list.length() == 3` |
| `SUM(path)` | Sum over a wildcard path | `SUM($.data.list[*].price)` |
| `SUM_PRODUCT(p1, p2)` | Element-wise product sum over two wildcard paths | `SUM_PRODUCT($.data.items[*].price, $.data.items[*].qty)` |

> This set of operators and functions is kept consistent with the [assertion engine of the python/ executor](../../python/docs/processors-and-report.en.md#assertion-engine).
