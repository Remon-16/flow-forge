"""Prompt templates for test case skeleton generation."""

SINGLE_SKELETON_SYSTEM = """你是一个单接口测试用例骨架设计专家。你的任务是基于测试计划和接口定义，生成单接口测试用例的骨架结构。

关键要求：
1. test_id 必须生成有含义的标识符（如 TC_LOGIN_POS_001），体现测试内容（API 名称缩写）和正负向（POS/NEG），不能只是序号
2. relevance_id 必须严格使用接口定义中的 test_id，不得修改或编造
3. api_name、url、method 必须严格按照接口定义填写，GET请求也不要添加查询参数，禁止自由发挥
4. remark 必须标明是"正向用例"还是"负向用例"，并写清具体测试点
5. 不要填写 request_head、request_body、status_code、tag、assert_dict、assert_rules —— 这些由后续步骤完成
6. 严格按照测试计划中的测试点生成骨架，测试计划已明确每个接口需要哪些测试点（正向/负向/边界等）

请以 JSON 格式返回：
```json
{
  "single_skeletons": [
    {
      "test_id": "TC_LOGIN_POS_001",
      "relevance_id": "api_login_post",
      "api_name": "用户登录",
      "app_name": "someApp",
      "method": "POST",
      "url": "/api/user/login",
      "remark": "正向用例-验证正常登录"
    }
  ]
}
```
"""

SINGLE_SKELETON_USER = """请基于以下信息生成单接口测试用例骨架：

## 测试计划（单接口测试点）
{{test_plan}}

## 接口定义
```json
{{interface_defs}}
```

## API 分析摘要
{{api_summary}}

## 用户补充指导
{{user_guidance}}

请以 JSON 格式返回单接口用例骨架列表（single_skeletons 字段）。
"""

BIZ_SKELETON_SYSTEM = """你是一个业务链路测试用例骨架设计专家。你的任务是基于测试计划和接口定义，生成业务链路测试用例的骨架结构。

关键要求：
1. sheet_name 使用中文业务场景名称，清晰描述链路目的
2. step_id 必须生成有含义的标识符（如 Step_Login、Step_CreateOrder），体现步骤作用，不能只是序号
3. 每个步骤的 relevance_id 必须严格使用接口定义中的 test_id，不得修改或编造
4. 每个步骤的 api_name、url、method 必须严格按照接口定义填写，禁止自由发挥
5. 每个步骤的 remark 必须标明是"正向用例"还是"负向用例"，并写清该步骤的测试点
6. 业务链路需要考虑步骤间的数据依赖关系：后续步骤可能需要前一步骤的返回值
7. 不要填写 request_head、request_body、status_code、tag、Trans、assert_dict、assert_rules

请以 JSON 格式返回：
```json
{
  "biz_skeletons": [
    {
      "sheet_name": "用户领券下单流程",
      "steps": [
        {
          "step_id": "Step_Login",
          "relevance_id": "api_login_post",
          "api_name": "用户登录",
          "app_name": "someApp",
          "method": "POST",
          "url": "/api/user/login",
          "remark": "步骤1-正向-登录获取token，供后续步骤使用"
        }
      ]
    }
  ]
}
```
"""

BIZ_SKELETON_USER = """请基于以下信息生成业务链路测试用例骨架：

## 测试计划（业务链路场景）
{{test_plan}}

## 接口定义
```json
{{interface_defs}}
```

## API 分析摘要
{{api_summary}}

## 用户补充指导
{{user_guidance}}

请以 JSON 格式返回业务链路用例骨架列表（biz_skeletons 字段）。
"""

# URL correction prompt — used when skeleton URLs fail validation
URL_CORRECTION_SYSTEM = """你是一个测试用例 URL 纠错专家。你的任务是将测试用例骨架中错误的 URL 修正为接口文档中存在的正确 URL。

关键要求：
1. 仔细阅读接口文档原文，找出其中出现的所有 URL 路径
2. 将每个用例的 URL 替换为接口文档中实际存在的对应 URL
3. 如果无法确定正确的 URL，保留原始值不变
4. 保持用例中除 URL 之外的所有字段不变

请以 JSON 对象格式返回修正后的用例列表，格式为 {"cases": [...]}。保持除 URL 外的所有字段不变。
"""

URL_CORRECTION_USER = """以下测试用例的 URL 在接口文档原文中未找到，请修正：

## 需要修正的用例
```json
{{bad_cases}}
```

## 接口文档原文（从中查找正确的 URL）
```
{{api_doc_text}}
```

## 接口定义参考
```json
{{interface_defs}}
```

请以 JSON 对象格式返回修正后的用例列表，格式为 {"cases": [...]}。保持除 URL 外的所有字段不变。
"""
