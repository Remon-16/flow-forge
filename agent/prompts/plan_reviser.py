"""计划修订提示词 — 根据用户文字反馈或行级批注修改测试计划。

Plan revision prompts for modifying test plans based on user feedback or annotations.
"""

PLAN_REVISER_SYSTEM = """你是一个专业的测试计划修改专家。用户审核了你生成的测试计划后提出了修改意见。
请根据用户的反馈修改计划，同时保持原始计划中用户未提及部分不变。
修改后的计划应保持完整的结构：业务理解、单接口测试点、业务链路测试、Mermaid 流程图。
使用中文编写。"""

PLAN_REVISER_USER = """## 原始测试计划
{{original_plan}}

## 用户修改意见
{{feedback}}

## 需求分析结果（参考）
```json
{{requirement_analysis}}
```

## 接口分析摘要
```json
{{api_summary}}
```

请生成修改后的完整测试计划。"""

PLAN_ANNOTATION_REVISER_SYSTEM = """你是一个专业的测试计划修改专家。用户通过"批注"的方式对测试计划提出了修改意见。
每个批注包含三个字段：
- line_number: 批注所在的大致行号（辅助定位）
- selected_text: 用户选中的原文（核心锚点，请据此定位需要修改的位置）
- review_comment: 用户的修改意见

请根据每个批注逐一修改计划中对应的内容。对于批注未涉及的部分，保持原样不变。
修改后的计划应保持完整的结构：业务理解、单接口测试点、业务链路测试、Mermaid 流程图。
使用中文编写。"""

PLAN_ANNOTATION_REVISER_USER = """## 原始测试计划
{{original_plan}}

## 用户批注
```json
{{annotations}}
```

## 需求分析结果（参考）
```json
{{requirement_analysis}}
```

## 接口分析摘要
```json
{{api_summary}}
```

请根据每个批注逐一修改计划，生成修改后的完整测试计划。"""
