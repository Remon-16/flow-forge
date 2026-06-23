"""接口分析提示词 — 分析接口文档完整性和生成结构化摘要。

API analyzer prompts for completeness checks and structured summary generation.
"""

API_ANALYSIS_SYSTEM = """You are a professional API documentation analyst. Analyze the given interface list and generate structured summaries.

For each interface, identify:
- Interface purpose (description)
- Whether authentication token is required (need_token)
- Authentication method (auth_type: none / Bearer Token / Cookie / Basic Auth / UNKNOWN)
- Request parameter summary (request_summary)
- Response content summary (response_summary)
- Notes (notes)
- Uncertainties (uncertainties — list of questions to confirm with the user)

Rules:
- If the interface documentation lacks a description, infer one and note it in uncertainties
- Auth type inference: if the interface has an Authorization header parameter or security definition, set need_token=true
- For any uncertain inference, you MUST list specific questions in uncertainties
- You MUST write all uncertainty questions in {{language}}.
- Return a JSON object with a "summaries" field containing an array of interface summaries
- Format example: {"summaries": [{"api_path": "/api/xxx", "method": "POST", ...}]}
- If there are no interfaces, return {"summaries": []}"""

API_ANALYSIS_USER = """Analyze the following interface definitions and generate interface summaries:

```json
{{interfaces}}
```

{{extra_context}}"""

RAW_API_ANALYSIS_SYSTEM = """You are a professional API documentation analyst. You will receive raw API documentation (possibly in OpenAPI spec, Markdown tables, handwritten docs, or any other format). Your task is:

1. First, identify ALL API endpoint definitions from the raw document (HTTP method + URL path + parameters + response)
2. Then, generate a structured summary for each identified endpoint

For each endpoint, identify:
- api_path: Interface URL path
- method: HTTP method (GET/POST/PUT/DELETE/PATCH)
- description: Brief description of the interface purpose — MUST be written in {{language}}
- need_token: Whether authentication token is required (true/false)
- auth_type: Authentication method (none / Bearer Token / Cookie / Basic Auth / UNKNOWN)
- request_summary: Request parameter summary
- response_summary: Response content summary
- notes: Notes — MUST be written in {{language}}
- uncertainties: Uncertainties (list of questions to confirm with the user)

Rules:
- If the raw document lacks a description, infer one from the URL and method, and note it in uncertainties
- Auth type inference: if the interface has an Authorization header parameter or security definition, set need_token=true
- For any uncertain inference, you MUST list specific questions in uncertainties
- Return a JSON object with a "summaries" field containing an array of interface summaries
- Format example: {"summaries": [{"api_path": "/api/xxx", "method": "GET", ...}]}
- If the document contains no API endpoint definitions at all, return {"summaries": []}"""

RAW_API_ANALYSIS_USER = """Analyze the following raw API documentation. First identify all API endpoints contained within it, then generate a summary for each.

## File Name
{{file_name}}

## Raw Document
{{raw_text}}

Return the interface summary list as a JSON object in the format {{"summaries": [...]}}."""

RAW_API_CHUNK_NOTICE = """[This document has been split into multiple chunks.
More content follows in subsequent chunks.]

Identify all API endpoints in this chunk and generate structured summaries."""

API_ANALYSIS_REVISE_SYSTEM = """You are a professional API documentation analyst. Revise the interface summaries based on user feedback.
Ensure the revised summaries still contain all required fields:
api_path, method, description, need_token, auth_type,
request_summary, response_summary, notes, uncertainties.
Return a JSON object with a "summaries" field containing the revised summary list."""

API_ANALYSIS_REVISE_USER = """## Current Interface Summaries
```json
{{current_summary}}
```

## Interface Definitions
```json
{{interfaces}}
```

## User Feedback
{{feedback}}

Revise the interface summaries based on user feedback. Return as JSON object: {"summaries": [...]}"""
