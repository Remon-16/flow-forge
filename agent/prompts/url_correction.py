"""URL 纠错提示词 — 将错误的 URL 修正为接口文档中存在的正确 URL。

URL correction prompts for fixing incorrect URLs based on API doc references.
"""

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
