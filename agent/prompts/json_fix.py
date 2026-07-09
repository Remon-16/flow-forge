"""JSON 修复提示词 — LLM 输出非合法 JSON 时的修复指令。

JSON fix prompt for when LLM outputs invalid JSON.
"""

JSON_FIX_PROMPT = """Your previous response was not valid JSON.
Below is the original task and your invalid/truncated response.
Please complete or fix the JSON and output ONLY a valid JSON object.
Do NOT include any markdown fences, explanatory text, or any other content."""
