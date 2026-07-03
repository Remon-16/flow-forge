# 文档解析提示词 — 从非结构化文档中提取接口定义。
# Doc parser prompts for extracting interface definitions from unstructured text.

from flow_forge_schemas.render import render_field_list, render_json_example

DOC_PARSER_SYSTEM = f"""You are an API documentation parsing expert. Your task is to extract API interface definitions from unstructured document text.

Extraction Rules:
1. Identify ALL API endpoints (HTTP method + URL path)
2. For each endpoint, extract the following information:
{render_field_list('interface_def', lang="en")}

3. Use reasonable defaults for fields that cannot be determined
4. If the document describes request parameters, fill request_body in "field_name": "example_value" format
5. If the document describes response fields, add them to assert_dict as check items
6. You MUST write api_name, remark, and all descriptive fields in {{language}}.

Return as a strict JSON object containing an "interfaces" field whose value is an array of interface definitions:
```json
{{
  "interfaces": [
    {render_json_example('interface_def')}
  ]
}}
```

Return ONLY the JSON object. Do NOT include any other explanatory text."""

DOC_PARSER_USER = """Please extract all API interface definitions from the following API document content.

## File Name
{{file_name}}

## Document Content
{{raw_text}}

## Hints
- File type hint: {{file_type_hint}}
- Read the full text carefully; do NOT miss any interfaces
- If the document content does not appear to contain API definitions, return an empty object {{"interfaces": []}}

Return a JSON object with the "interfaces" field containing the list of interface definitions."""

DOC_CHUNK_NOTICE = """[This document has been split into multiple chunks.
More content follows in subsequent chunks.]

Extract all API interface definitions from this chunk."""

DOC_DEFAULT_FILE_TYPE_HINT = "Unknown format"
