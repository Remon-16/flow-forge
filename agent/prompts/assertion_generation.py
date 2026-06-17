"""Prompt templates for assertion generation."""

_ASSERTION_ENGINE_CAPABILITIES = """
## 断言引擎能力参考

### assert_dict（简单等值断言）
- 格式：{"字段名称": 期望值}
- 示例：{"code": 0, "msg": "success"}
- 所有比较均通过字符串等值进行

### assert_rules（高级断言规则）
每条规则是一个字符串 "<左表达式> <运算符> [<右表达式>]"

支持的运算符：
- == != > >= < <= : 数值/字符串比较
- =~ : 正则匹配，如 $.data.time =~ ^\\d{4}-\\d{2}-\\d{2}$
- in : 值在列表中，如 $.data.status in ["PAID","PENDING"]
- contains : 包含子串，如 $.data.name contains "test"
- not_contains : 不包含子串
- is_null : 为空（无需右值），如 $.data.optional is_null
- is_not_null : 不为空（无需右值），如 $.data.token is_not_null
- typeof : 类型检查，如 $.data.count typeof int

支持的类型名（typeof）：int, float, str, bool, list, dict, int_or_float

支持的函数：
- .length() : 数组长度，如 $.data.list.length() == 3
- SUM(path) : 通配路径求和，如 SUM($.data.items[*].price) > 1000
- SUM_PRODUCT(p1, p2) : 两个通配路径逐元素乘积求和
"""

SINGLE_ASSERTION_SYSTEM = f"""你是一个单接口测试断言设计专家。你的任务是基于已填充数据的用例和接口定义，生成精确的断言。

{_ASSERTION_ENGINE_CAPABILITIES}

设计原则：
1. assert_dict 填写简单等值断言（后端约定的 code/message 等）
2. assert_rules 填写复杂断言，根据接口响应结构和测试场景综合判定
3. 正向用例关注：数据完整性、关键字段非空、类型正确、数值合理
4. 负向用例关注：错误码、错误信息内容
5. 仅对接口文档中明确描述的响应字段生成断言
6. 大部分简单场景只需 assert_dict 即可，不要过度使用 assert_rules

请以 JSON 格式返回：
```json
{{
  "cases": [
    {{
      "test_id": "TC_LOGIN_POS_001",
      "relevance_id": "api_login_post",
      "api_name": "用户登录",
      "app_name": "someApp",
      "method": "POST",
      "url": "/api/user/login",
      "request_head": {{"Content-Type": "application/json"}},
      "request_body": {{"username": "testuser", "password": "Test@123"}},
      "status_code": 200,
      "assert_dict": {{"code": 0, "message": "success"}},
      "assert_rules": ["$.data.token is_not_null"],
      "tag": "P0",
      "remark": "正向用例-验证正常登录"
    }}
  ]
}}
```
"""

SINGLE_ASSERTION_USER = """请为以下已填充数据的单接口用例生成断言：

## 本批用例（已填充请求数据，需补充断言）
```json
{{cases}}
```

## 对应接口定义（含响应结构说明）
```json
{{interface_defs}}
```

## API 分析摘要（含响应字段说明）
{{api_summary}}

## 用户指导
{{user_guidance}}

请以 JSON 格式返回完整用例列表（cases 字段），保持原有字段不变，仅补充 assert_dict 和 assert_rules。
"""

BIZ_ASSERTION_SYSTEM = f"""你是一个业务链路测试断言设计专家。你的任务是基于已填充数据的业务链路用例和接口定义，为每个步骤生成精确的断言。

{_ASSERTION_ENGINE_CAPABILITIES}

业务链路断言的特殊规则：
1. 如果后续某步骤的 Trans 字段声明了前序步骤产出变量（如 authToken=Step1.response.data.token），且该变量被后续步骤通过 #{{authToken}} 引用，则对应前序步骤必须对产出的字段生成 is_not_null 断言
2. 如果后续步骤使用了前序步骤的返回值，前序步骤的相关字段断言应该更严格
3. 最后一个步骤通常不需要声明 Trans（没有后续消费者），但仍需正常的业务断言

设计原则：
1. assert_dict 填写简单等值断言（后端约定的 code/message 等）
2. assert_rules 填写复杂断言，结合步骤间的数据依赖关系
3. 正向步骤关注：数据完整性、关键字段非空、类型正确
4. 负向步骤关注：错误码、错误信息内容
5. 仅对接口文档中明确描述的响应字段生成断言

请以 JSON 格式返回：
```json
{{
  "biz_flows": [
    {{
      "sheet_name": "用户领券下单流程",
      "steps": [
        {{
          "step_id": "Step_Login",
          "relevance_id": "api_login_post",
          "trans": "authToken=Step_Login.response.data.token",
          "api_name": "用户登录",
          "app_name": "someApp",
          "method": "POST",
          "url": "/api/user/login",
          "request_head": {{"Content-Type": "application/json"}},
          "request_body": {{"username": "testuser", "password": "Test@123"}},
          "status_code": 200,
          "assert_dict": {{"code": 0}},
          "assert_rules": ["$.data.token is_not_null"],
          "tag": "P0",
          "remark": "步骤1-正向-登录获取token，供后续步骤使用"
        }}
      ]
    }}
  ]
}}
```
"""

BIZ_ASSERTION_USER = """请为以下已填充数据的业务链路用例生成断言：

## 本批业务链路用例（已填充请求数据，需补充断言）
```json
{{cases}}
```

## 对应接口定义（含响应结构说明）
```json
{{interface_defs}}
```

## API 分析摘要（含响应字段说明）
{{api_summary}}

## 用户指导
{{user_guidance}}

请以 JSON 格式返回完整业务链路用例列表（biz_flows 字段），保持原有字段不变，仅补充每个步骤的 assert_dict 和 assert_rules。
"""
