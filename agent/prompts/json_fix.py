"""JSON 修复提示词 — LLM 输出非合法 JSON 时的修复指令。

JSON fix prompt for when LLM outputs invalid JSON.
"""

JSON_FIX_PROMPT = """Your previous response was not valid JSON.
You MUST output ONLY a single JSON object. Do NOT include any markdown
fences, explanatory text, or any other content besides the JSON object
itself."""
