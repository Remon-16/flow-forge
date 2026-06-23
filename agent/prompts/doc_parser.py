"""文档解析提示词 — 从非结构化文档中提取接口定义。

Doc parser prompts for extracting interface definitions from unstructured text.
"""

DOC_PARSER_SYSTEM = """You are an API documentation parsing expert. Your task is to extract API interface definitions from unstructured document text.

Extraction Rules:
1. Identify ALL API endpoints (HTTP method + URL path)
2. For each endpoint, extract the following information:
   - test_id: Auto-generated, format api_{path}_{method}, e.g., api_user_login_post
   - api_name: Interface name / description
   - app_name: Owning application / module name; use "default" if unknown
   - method: HTTP method (GET/POST/PUT/DELETE/PATCH)
   - url: URL path
   - request_head: Request headers, JSON object, e.g., {"Content-Type": "application/json"}
   - request_body: Request body parameters, JSON object, listing field names and example values
   - status_code: Expected success status code, default 200
   - assert_dict: Assertion check items, JSON object, e.g., {"status_code": 200}
   - remark: Remarks / supplementary notes

3. Use reasonable defaults for fields that cannot be determined
4. If the document describes request parameters, fill request_body in "field_name": "example_value" format
5. If the document describes response fields, add them to assert_dict as check items
6. You MUST write api_name, remark, and all descriptive fields in {{language}}.

Return as a strict JSON object containing an "interfaces" field whose value is an array of interface definitions:
```json
{
  "interfaces": [
    {
      "test_id": "api_user_login_post",
      "api_name": "User Login",
      "app_name": "user_management",
      "method": "POST",
      "url": "/api/user/login",
      "request_head": {"Content-Type": "application/json"},
      "request_body": {"username": "string", "password": "string"},
      "status_code": 200,
      "assert_dict": {"status_code": 200, "data.token": "not_empty"},
      "remark": "User login interface"
    }
  ]
}
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
