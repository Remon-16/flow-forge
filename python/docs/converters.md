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

将用例转换为原生、独立的 pytest 代码，**不依赖 Flow Forge 执行器框架**。纯逻辑处理器仅需 `pytest` + `requests`；中间件处理器（Redis/MQ/RocketMQ/DB）运行时依赖对应第三方库（`redis`、`kombu`、`sqlalchemy`、`pymysql`、`jaydebeapi`、`JPype1` 等）。生成的代码可复制到安装好这些依赖的项目直接运行，适合分享给其他团队或集成到 CI/CD。

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
    conftest.py                  # fixtures + 所有辅助函数 + 处理器调度
    _config.py                   # 环境选择器（ENV = "local" → 导入对应 _env_*.py）
    _env_local.py                # 每个环境独立的 app 配置（从 env-*.yml 解析）
    _ff_compat.py                # 兼容层（基类再导出 + 最小 i18n + app 配置访问）
    _processors/                 # 整包复制 python/processors（builtin 全量 + 基础模块，import 已重写）
    _auth/                       # 处理器依赖的登录管理模块（import 已重写）
    _resolvers/                  # 处理器依赖的路径/占位符解析模块（import 已重写）
    test_single_cases.py         # 单接口用例
    test_biz_flows.py            # 业务流用例
```

### 生成代码特点

- 请求头/请求体提取为文件顶部的 Python 常量，方便直接修改调试
- 完整的内置断言规则引擎（多运算符 + SUM/SUM_PRODUCT/长度聚合函数）
- 整包复制 `python/processors/`（含 builtin 全量与 `base.py`/`redis.py`/`mq.py`/`db.py`/`rocketmq.py` 等基础模块）及其配套依赖（`auth/`、`resolvers/`），统一重写 Flow Forge import；后续新增内置处理器或用户自定义处理器无需再改转换器
- 登录/Token 管理自动转换为 `_resolve_token()` + `_do_login()` 辅助函数，保持 Token 缓存
- 自定义处理器复制到 `_processors/` 根目录，通过 `_ff_compat.py` 兼容层与 import 重写实现零修改打包

---

## 推荐工作流

最推荐的工作方式：**AI 生成 Excel → Studio 批量编辑 → 转 YAML 做 git diff → 执行器运行**。

1. 在 [Flow Forge Studio](../../studio/README.md) 的「AI 用例生成」中配置文档并启动智能体，生成 Excel 用例。
2. 在 Studio 的 Excel 编辑器中批量调整 Tag、补全参数、修改断言。
3. 用 `excel2yaml`（CLI 或 Studio 的「用例转换器」）转为 YAML 纳入 Git 版本控制——YAML 每个用例一个文件，git diff 可清晰展示每次变更。
4. 需要分享或集成 CI/CD 时，用 `yaml2pytest` / `excel2pytest` 生成独立 pytest 文件。

调试好 Skill 和插件后，可在 CLI 下用 `--auto` 模式跳过人工审核，适合夜间批量生成。
