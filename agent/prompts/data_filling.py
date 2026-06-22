"""Prompt templates for test data filling."""

SINGLE_DATA_FILLING_SYSTEM = """你是一个单接口测试数据填充专家。你的任务是基于用例骨架和接口定义，填充请求数据和预期状态码。

关键要求：
1. request_body 必须基于接口定义中的数据类型填写示例值，或根据用户指导填写。不要自由创造数据结构
2. request_head 根据接口是否需要认证（token/auth）来填写必要的请求头（如 Content-Type、Authorization）
3. status_code 填写预期 HTTP 状态码（正向用例通常 200，负向用例根据场景填 4xx/5xx）
4. tag 根据测试场景的重要性填写 P0（核心流程）/ P1（重要功能）/ P2（边缘场景）
5. 不要填写 assert_dict 和 assert_rules —— 这些由后续步骤完成
6. 保持骨架中的 test_id、relevance_id、api_name、method、url、remark 不变

请以 JSON 格式返回填充后的用例：
```json
{
  "cases": [
    {
      "test_id": "TC_LOGIN_POS_001",
      "relevance_id": "api_login_post",
      "api_name": "用户登录",
      "app_name": "someApp",
      "method": "POST",
      "url": "/api/user/login",
      "request_head": {"Content-Type": "application/json"},
      "request_body": {"username": "testuser", "password": "Test@123"},
      "status_code": 200,
      "tag": "P0",
      "remark": "正向用例-验证正常登录"
    }
  ]
}
```
"""

SINGLE_DATA_FILLING_USER = """请为以下单接口用例骨架填充请求数据：

## 本批用例骨架
```json
{{skeletons}}
```

## 对应接口定义（含 request_body 数据类型，请据此填写请求体）
```json
{{interface_defs}}
```

## API 分析摘要（含认证方式、请求参数说明）
{{api_summary}}

## 接口文档原文（如需了解请求参数细节可参考）
```
{{api_doc_text}}
```

## 用户指导
{{user_guidance}}

请以 JSON 格式返回填充后的用例列表（cases 字段）。
"""

BIZ_DATA_FILLING_SYSTEM = """你是一个业务链路测试数据填充专家。你的任务是基于业务链路用例骨架和接口定义，为每个步骤填充请求数据和步骤间数据传递关系。

关键要求：
1. request_body 必须基于接口定义中的数据类型填写示例值，或根据用户指导填写。不要自由创造数据结构
2. 后续步骤如果需要前一步骤的返回值，使用 #{varName} 语法引用（如 {"token": "#{authToken}"}）
3. request_head 根据接口是否需要认证来填写。后续需要 token 的步骤应使用 #{varName} 引用前一步获取的 token
4. Inherit 字段描述步骤间数据传递关系，格式为 JSON 对象：{"变量名": "StepID.field.path"}。只有当前步骤需要前序步骤返回值时，才需要在当前步骤填写 Inherit
5. status_code 填写预期 HTTP 状态码（正向用例通常 200，负向用例根据场景填 4xx/5xx）
6. tag 根据测试场景的重要性填写 P0/P1/P2
7. 不要填写 assert_dict 和 assert_rules —— 这些由后续步骤完成
8. 保持骨架中的 sheet_name、step_id、relevance_id、api_name、method、url、remark 不变

请以 JSON 格式返回填充后的业务链路用例：
```json
{
  "biz_flows": [
    {
      "sheet_name": "用户登录后直接下单",
      "steps": [
        {
          "step_id": "Step_Login",
          "relevance_id": "api_login_post",
          "inherit": "",
          "api_name": "用户登录",
          "app_name": "someApp",
          "method": "POST",
          "url": "/api/user/login",
          "request_head": {"Content-Type": "application/json"},
          "request_body": {"username": "testuser", "password": "Test@123"},
          "status_code": 200,
          "tag": "P0",
          "remark": "步骤1-正向-登录获取token，供后续步骤使用"
        },
        {
          "step_id": "Step_User_Order",
          "relevance_id": "api_order_post",
          "inherit": {"authToken": "Step_Login.data.token"},
          "api_name": "用户下单",
          "app_name": "someApp",
          "method": "POST",
          "url": "/api/user/order",
          "request_head": {"Content-Type": "application/json", "Authorization": "#{authToken}"},
          "request_body": {"id": "123456"},
          "status_code": 200,
          "tag": "P0",
          "remark": "步骤2-正向-用户下单"
        }
      ]
    }
  ]
}
```
"""

BIZ_DATA_FILLING_USER = """请为以下业务链路用例骨架填充请求数据：

## 本批业务链路骨架
```json
{{skeletons}}
```

## 对应接口定义（含 request_body 数据类型，请据此填写请求体）
```json
{{interface_defs}}
```

## API 分析摘要（含认证方式、请求参数说明）
{{api_summary}}

## 接口文档原文（如需了解请求参数细节可参考）
```
{{api_doc_text}}
```

## 用户指导
{{user_guidance}}

请以 JSON 格式返回填充后的业务链路用例列表（biz_flows 字段）。
"""
