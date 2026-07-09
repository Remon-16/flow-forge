# 用例格式转换（converter）

[← 返回 python/README](../README.md)

`python/converter/` 子包提供 Excel 与 YAML 用例格式的双向转换，以及 YAML/Excel → 独立 pytest 代码生成。入口文件为 `python/converter_main.py`，四个子命令：`excel2yaml`、`yaml2excel`、`yaml2pytest`、`excel2pytest`。

---

## excel2yaml — Excel → YAML

```bash
python converter_main.py excel2yaml --input cases.xlsx --output ./output/
```

读取 Excel 工作簿，按 Sheet 分类提取：`API Definitions` → `interfaces/`，`Single Cases` → `single_cases/`，其余 Sheet → `biz_flows/`。每个条目生成一个 `.yaml` 文件，JSON 列自动解析为对象，字段名从 PascalCase 转为 snake_case。

| 参数 | 说明 |
|------|------|
| `--input`, `-i` | 输入 `.xlsx` 文件路径（必填） |
| `--output`, `-o` | 输出 YAML 目录（必填） |
| `--verbose`, `-v` | 启用调试日志 |

---

## yaml2excel — YAML → Excel

```bash
python converter_main.py yaml2excel \
  --interfaces ./cases/interfaces/ \
  --single-cases ./cases/single_cases/ \
  --biz-flows ./cases/biz_flows/ \
  --output cases.xlsx
```

三个输入目录均为可选——不提供的目录在生成的 Excel 中对应 Sheet 留空（仅写表头）。YAML 需符合 Flow Forge 用例格式（含 `case_type` 字段，或通过结构自动推断类型）。

| 参数 | 说明 |
|------|------|
| `--interfaces` | 接口定义 YAML 目录（可选） |
| `--single-cases` | 单接口用例 YAML 目录（可选） |
| `--biz-flows` | 业务链路 YAML 目录（可选） |
| `--output`, `-o` | 输出 `.xlsx` 文件路径（必填） |
| `--verbose`, `-v` | 启用调试日志 |

---

## yaml2pytest / excel2pytest — 生成独立 pytest 代码

将用例转换为原生、独立的 pytest 代码，**零 Flow Forge 依赖**，仅需 `pytest` + `requests`。生成的代码可复制到任意项目直接运行，适合分享给其他团队或集成到 CI/CD。

```bash
# YAML → pytest（三个目录均可选，至少提供一个）
python converter_main.py yaml2pytest \
    --interfaces ./cases/interfaces/ \
    --single-cases ./cases/single_cases/ \
    --biz-flows ./cases/biz_flows/ \
    --output ./tests/generated/

# Excel → pytest（自动检测 Sheet 类型）
python converter_main.py excel2pytest \
    --input cases.xlsx \
    --output ./tests/generated/

# 可选参数
python converter_main.py yaml2pytest ... --config-dir .                  # env-*.yml 所在目录
python converter_main.py yaml2pytest ... --processors-dir ./processors/  # 自定义处理器目录
```

| 参数 | 适用 | 说明 |
|------|------|------|
| `--interfaces` / `--single-cases` / `--biz-flows` | yaml2pytest | YAML 输入目录（可选，至少一个） |
| `--input`, `-i` | excel2pytest | 输入 `.xlsx` 文件（必填） |
| `--output`, `-o` | 两者 | 输出目录（必填） |
| `--config-dir` | 两者 | `env-*.yml` 所在目录（默认 `python/`） |
| `--processors-dir` | 两者 | 自定义处理器目录 |
| `--verbose`, `-v` | 两者 | 启用调试日志 |

### 生成的文件结构

```
output_dir/
    conftest.py                  # fixtures + 所有辅助函数 + 内置处理器独立实现
    _config.py                   # 环境选择器（ENV = "local" → 导入对应 _env_*.py）
    _env_local.py                # 每个环境独立的 app 配置（从 env-*.yml 解析）
    _ff_compat.py                # 轻量兼容层（PreProcessor/PostProcessor/ProcessorError 桩）
    _custom_processors/          # 用户自定义处理器原样复制（自动替换 import 路径）
    test_single_cases.py         # 单接口用例
    test_biz_flows.py            # 业务流用例
```

### 生成代码特点

- 请求头/请求体提取为文件顶部的 Python 常量，方便直接修改调试
- 完整的内置断言规则引擎（多运算符 + SUM/SUM_PRODUCT/长度聚合函数）
- 内置处理器全部转为独立函数（`_apply_timestamp()`、`_apply_hmac_sign()` 等），零框架依赖
- 登录/Token 管理自动转换为 `_resolve_token()` + `_do_login()` 辅助函数，保持 Token 缓存
- 自定义处理器通过 `_ff_compat.py` 兼容层实现零修改打包

---

## 推荐工作流

先用 AI 智能体生成 Excel 用例（`--output-format excel`），在 [Flow Forge Studio](../../studio/README.md) 中批量编辑（调整 Tag、补全参数、修改断言），再用 `excel2yaml` 转为 YAML 纳入 Git 版本控制——YAML 每个用例一个文件，git diff 可清晰展示每次变更，方便代码评审。需要分享或集成 CI/CD 时，用 `yaml2pytest` / `excel2pytest` 生成独立 pytest 文件。
