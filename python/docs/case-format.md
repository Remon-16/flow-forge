# 用例格式

[← 返回 python/README](../README.md)

执行器支持两种用例格式：**YAML**（智能体默认输出，推荐）和 **Excel**。两者语义一致，可通过[转换器](./converters.md)互转。

---

## YAML 用例格式

每个用例是一个独立的 `.yaml` 文件，通过 `case_type` 字段区分类型。

### 单接口用例（case_type: single）

```yaml
case_type: single
test_id: TC_LOGIN_001
api_name: 用户登录
app_name: someApp
method: POST
url: /api/user/login
request_head:
  Content-Type: application/json
request_body:
  username: admin
  password: "123456"
status_code: 200
assert_dict:
  $.code: 0
  $.msg: success
assert_rules:
  - "$.data.token is_not_null"
tag: P0
remark: 正常登录验证
```

### 业务链路用例（case_type: biz）

```yaml
case_type: biz
sheet_name: 用户注册并登录流程
steps:
  - step_id: Step01
    api_name: 发送验证码
    app_name: someApp
    method: POST
    url: /api/sms/send
    request_body:
      phone: "13800138000"
    status_code: 200
    assert_dict:
      $.code: 0
    inherit:
      smsCode: Step01.data.code
  - step_id: Step02
    api_name: 用户注册
    app_name: someApp
    method: POST
    url: /api/user/register
    request_body:
      phone: "13800138000"
      code: "#{smsCode}"
      password: "123456"
    status_code: 200
    assert_dict:
      $.code: 0
```

### YAML 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `case_type` | str | 用例类型：`single`（单接口）或 `biz`（业务链路） |
| `test_id` | str | 唯一测试用例标识（单接口用例必填） |
| `api_name` | str | 接口名称/描述 |
| `app_name` | str | 应用名，对应 `env-{envName}.yml` 中的 app key |
| `method` | str | HTTP 方法：`GET`/`POST`/`PUT`/`DELETE`/`PATCH` |
| `url` | str | 接口路径（相对于 app 的 `baseURL`），如 `/api/user/login` |
| `status_code` | int | 预期 HTTP 状态码 |
| `request_head` | dict | 请求头，key-value 对象 |
| `request_body` | dict | 请求体，key-value 对象 |
| `assert_dict` | dict | 简单断言字典，key 为响应 JSON 路径，value 为预期值 |
| `assert_rules` | list[str] | 高级断言规则列表（可选），每条为字符串表达式 |
| `tag` | str | 标签（如 P0/P1/P2） |
| `remark` | str | 备注 |
| `sheet_name` | str | 业务场景名（业务链路用例必填） |
| `steps` | list | 业务链路步骤列表（业务链路用例必填） |
| `step_id` | str | 步骤标识（同一业务链路内不可重复），如 `Step01` |
| `inherit` | dict | 步骤间数据传递定义，原生映射格式，语法见下 |

断言运算符与函数的完整参考见 [处理器与报告](./processors-and-report.md#断言引擎) 中的断言引擎章节。

---

## Excel 用例格式

Excel 文件包含多张 Sheet：

### Sheet 1 — API Definitions（接口定义）

必填列：`TestID`、`APIName`、`AppName`、`Method`、`URL`、`StatusCode`

| 列名 | 类型 | 说明 |
|------|------|------|
| `TestID` | str | 唯一标识，被其他 Sheet 的 `RelevanceID` 引用 |
| `APIName` | str | 接口名称/描述 |
| `AppName` | str | 应用名，对应 `env-{envName}.yml` 中的 app key |
| `Method` | str | HTTP 方法 |
| `URL` | str | 接口路径（相对于 `baseURL`） |
| `StatusCode` | int | 预期 HTTP 状态码 |
| `RequestHead` | JSON | 请求头，JSON 字符串或对象 |
| `RequestBody` | JSON | 请求体，JSON 字符串或对象 |
| `AssertDict` | JSON | 断言字典 |
| `Remark` | str | 备注 |
| `Tag` | str | 标签 |

> Sheet 1 仅作为智能体的参考文档，**执行器不读取此页**。用例行的值直接使用，不与 Sheet 1 合并或自动填充。`RelevanceID` 用于关联参考，主要供用例生成智能体索引查询。

### Sheet 2 — Single Cases（单接口用例）

必填列：`TestID`、`RelevanceID`

| 列名 | 说明 |
|------|------|
| `TestID` | 唯一测试用例标识 |
| `RelevanceID` | 关联到 Sheet 1 的 `TestID`（执行器不强制校验） |
| 其他列 | 同 Sheet 1，用例行的值直接使用 |

### Sheet 3+ — Business Flow（业务链路用例）

每个 Sheet 代表一个业务场景，Sheet 名即为场景名。必填列：`StepID`、`RelevanceID`

| 列名 | 说明 |
|------|------|
| `StepID` | 步骤标识（同一 Sheet 内不可重复） |
| `RelevanceID` | 关联到 Sheet 1 的 `TestID`（执行器不强制校验） |
| `Inherit` | 步骤间数据传递定义，JSON 字符串格式 |
| 其他列 | 同 Sheet 1/2 |

### JSON 字段支持的格式

- 标准 JSON 字符串（双引号）
- 单引号 JSON（自动转换为双引号）
- 中文引号 `“”`/`‘’`（自动转换为标准双引号）
- 直接 JSON 对象（openpyxl 读取时已解析为 dict）

---

## Inherit 字段语法

`Inherit` 用于在业务链路的步骤之间传递数据，格式为 JSON 对象（YAML 中使用原生映射）：

```yaml
# YAML 格式（原生映射）
inherit:
  变量名: 来源StepID.响应JSON路径
  变量名2: 来源StepID2.响应JSON路径
```

Excel 单元格中以 JSON 字符串存储：`{"变量名": "来源StepID.响应JSON路径"}`。

在 `request_head`、`request_body` 或 `url` 路径中使用 `#{变量名}` 引用传递的值。URL 路径参数示例 `/api/users/#{userId}/orders/#{orderId}`，其中的占位符会从当前步骤 `request_body` 取值替换。

转义：使用 `\#{...}` 表示字面量 `#{...}`，不会被替换。

### 通过 Inherit 传递登录 Token 的完整示例

```yaml
case_type: biz
sheet_name: 用户注册登录并下单流程
steps:
  - step_id: Step_Register
    api_name: 用户注册
    app_name: someApp
    method: POST
    url: /api/user/register
    request_body:
      phone: "13800138000"
      password: "123456"
    status_code: 200
    # 此步骤没有 inherit —— 响应自动存储，供后续步骤引用

  - step_id: Step_Login
    api_name: 用户登录
    app_name: someApp
    method: POST
    url: /api/user/login
    request_body:
      phone: "13800138000"
      password: "123456"
    status_code: 200
    inherit:
      authToken: Step_Login.data.token
      userId: Step_Login.data.id

  - step_id: Step_CreateOrder
    api_name: 创建订单
    app_name: someApp
    method: POST
    url: /api/order/create
    request_head:
      Content-Type: application/json
      Authorization: "Bearer #{authToken}"   # 从 Inherit 获取，不走 LoginManager
    request_body:
      userId: "#{userId}"                     # 从 Inherit 获取
      productId: "PROD_001"
      quantity: 1
    status_code: 200
```

上例中，`Step_CreateOrder` 的 `Authorization: "Bearer #{authToken}"` 会从 `Step_Login` 的响应取 token，而非从 LoginManager 的预配置凭据获取——因为 Inherit 中声明了 `authToken`，执行器识别为已提供，跳过 LoginManager。

### Inherit 校验规则

- 不允许包含中文字符
- 必须是 `key=value`（键值）格式
- 方括号 `[]` 必须成对出现
- 同一 Sheet / 业务链路内 `StepID` 不可重复
