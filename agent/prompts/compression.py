"""对话压缩提示词 — 压缩 LLM 对话历史为关键要点摘要。

Conversation compression prompts for condensing conversation history.
"""

COMPRESSION_SYSTEM = """Condense the following conversation history and
intermediate results into a concise summary of key points. This summary will
be used as context for subsequent processing rounds — preserve all information
that is necessary to maintain consistency across rounds. Preserve all
important data, conclusions, and decisions. Discard redundant content and
unnecessary details.

History:
{history}"""

# Default chunk notice for _process_long_text (used when caller does not provide one)
DEFAULT_CHUNK_NOTICE = """[This is chunk {i}/{total}. More content follows.
Continue processing.]"""
# 注意：此常量走 Python .format(i=..., total=...)，使用单花括号
