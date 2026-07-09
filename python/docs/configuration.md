# 配置与命令行参考

[← 返回 python/README](../README.md)

本文档覆盖执行器的安装依赖、配置文件（`env.yml` + `env-{envName}.yml`）、命令行参数与执行模式。

---

## 安装

```bash
cd python
pip install -r requirements.txt
```

### 依赖说明

| 依赖 | 用途 |
|------|------|
| `requests` | HTTP 请求发送 |
| `openpyxl` | Excel 用例文件读取 |
| `pyyaml` | YAML 配置文件解析 |
| `pytest` | 运行内置测试套件（`tests/`），执行用例本身不依赖 |

---

## 配置优先级

```
CLI 参数 > env-{envName}.yml > env.yml > 内置默认值
```

## env.yml — 基础配置（可提交）

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `scriptType` | str | `APITest` | 脚本类型（目前仅 `APITest`） |
| `envName` | str | 必填 | 环境名称，对应加载 `env-{envName}.yml` |
| `caseFilePath` | str | 必填 | Excel 用例文件路径（相对路径相对于 main.py） |
| `maxThread` | int | `5` | 线程池大小，控制并发数 |
| `reportName` | str | `APIReport` | HTML 报告标题 |
| `apiMode` | str | `single` | 执行模式：`single` / `biz` / `all` |
| `lang` | str | `zh_CN` | 界面语言：`zh_CN` / `en_US` |
| `excel_font` | str | `微软雅黑` | Excel 导出字体名称 |

> **`excel_font` 作用范围**：仅 Python 转换器的 Excel 写入（`converter/excel_writer.py`）会读取此配置。Studio 的 Excel 导出字体是硬编码的（`微软雅黑`），不受此项影响。

必填项：`envName`、`caseFilePath`（缺失时以退出码 2 终止）。

## env-{envName}.yml — 环境配置（不可提交，含凭据）

顶层 dict key 即为「应用名」，与用例中 `app_name` / `AppName` 的值对应。

```yaml
<AppName>:
  baseURL: http://localhost:8080        # 应用基础 URL
  loginPath: /api/user/login            # 登录接口路径
  loginBody: userAccount,password       # 登录请求体字段列表（逗号分隔）
  headTokenName: Authorization          # Token 在请求头中的字段名
  resTokenPath: $.data.token            # 登录响应中 Token 的 JSON 路径
  <userParamName>:                      # 用户配置（名称在用例中通过 #{} 引用）
    userAccount: admin                  # loginBody 中字段的值
    password: "123456"
```

可定义多个应用，每个应用可有多个用户：

```yaml
someApp:
  baseURL: http://localhost:8080
  loginPath: /api/login
  loginBody: userAccount,password
  headTokenName: Authorization
  resTokenPath: $.data.token
  adminUser:
    userAccount: user1
    password: "12345678"
  leaderUser:
    userAccount: user2
    password: "12345678"

managerURL:
  baseURL: http://localhost:8081
  loginPath: /api/manager/login
  loginBody: username,password
  headTokenName: Authorization
  resTokenPath: $.data.token
  someUser:
    username: usera1
    password: 11111*
```

### processor_configs — 处理器敏感数据

数据库连接、密钥等敏感信息不应写在用例里，可在配置文件的 `processor_configs` 段声明，执行时自动传递到处理器的 `global_config` 参数：

```yaml
processor_configs:
  hmac-sign:
    secret_env: SIGN_SECRET
    algorithm: sha256
  sql-cleanup:
    host: localhost
    port: 3306
    database: testdb
```

详见 [处理器与报告](./processors-and-report.md#前置处理器--后置处理器)。

---

## 命令行参数

主入口 `python main.py`（与 `main.py` 的 argparse 一致）：

| 参数 | 类型 | 说明 |
|------|------|------|
| `--config` | str | `env.yml` 路径（默认：main.py 同级目录下的 `env.yml`） |
| `--scriptType` | str | 脚本类型，覆盖 env.yml |
| `--envName` | str | 环境名称，覆盖 env.yml |
| `--caseFilePath` | str | Excel 用例文件路径，覆盖 env.yml |
| `--maxThread` | int | 最大线程数，覆盖 env.yml |
| `--reportName` | str | 报告名称，覆盖 env.yml |
| `--apiMode` | str | 执行模式（`single`/`biz`/`all`），覆盖 env.yml |
| `--yamlDir` | str | YAML 用例目录路径，递归扫描目录下所有 `.yaml`/`.yml` 文件 |
| `--yamlFiles` | str | 逗号分隔的 YAML 用例文件路径列表 |
| `--verbose`, `-v` | flag | 启用调试日志 |

### apiMode 说明

| 值 | 行为 |
|----|------|
| `single` | 仅执行单接口用例（YAML: `case_type=single`；Excel: Sheet 2） |
| `biz` | 仅执行业务链路用例（YAML: `case_type=biz`；Excel: Sheet 3+） |
| `all` | 同时执行单接口和业务链路用例 |

命令示例见 [python/README.md 快速开始](../README.md)。

---

## 退出码

| 退出码 | 含义 |
|--------|------|
| `0` | 所有用例通过 |
| `1` | 部分或全部用例失败 |
| `2` | 配置错误或文件解析错误（未执行任何用例） |
