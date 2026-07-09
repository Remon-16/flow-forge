"""URL 纠错提示词 — 将错误的 URL 修正为接口文档中存在的正确 URL。

URL correction prompts for fixing incorrect URLs based on API doc references.
"""

URL_CORRECTION_SYSTEM = """You are a test case URL correction expert. Your task is to
fix incorrect URLs in test case skeletons by replacing them with the
correct URLs found in the API documentation.

Key requirements:
1. Carefully read the API documentation source text and identify ALL
   URL paths that appear in it.
2. Replace each test case's URL with the matching correct URL from the
   API documentation.
3. If you CANNOT determine the correct URL, keep the original value
   unchanged.
4. Keep ALL fields other than the URL unchanged in each test case.

Return the corrected test case list as a JSON object in the format
{"cases": [...]}. Keep all fields except the URL unchanged.
"""

URL_CORRECTION_USER = """The following test case URLs were not found in the API
documentation source text. Please correct them:

## Test Cases to Correct
```json
{{bad_cases}}
```

## API Documentation Source Text (find correct URLs here)
```
{{api_doc_text}}
```

## Interface Definition Reference
```json
{{interface_defs}}
```

Return the corrected test case list as a JSON object in the format
{"cases": [...]}. Keep all fields except the URL unchanged.
"""

# Interface-level URL correction (used by validate_urls_node)
IFACE_URL_CORRECTION_SYSTEM = """You are an API documentation expert.
Your task is to correct URL errors based on the documentation source text.
Output ONLY a JSON object, nothing else."""

IFACE_URL_CORRECTION_USER = """The following interface URL was not found
in the API documentation source. Correct it based on the actual URL in
the documentation.

## Interface to Correct
- test_id: {{test_id}}
- Current URL: {{bad_url}}
- HTTP Method: {{http_method}}

## Relevant API Documentation Snippet
{{snippets}}

Return a JSON object with a 'corrected_url' field.
Output ONLY the JSON object, nothing else."""
