"""Built-in tools for ReAct agents."""

from pathlib import Path
from typing import Any, Dict, List, Optional

from ..registry import ToolRegistry


# ------------------------------------------------------------------
# File read tool
# ------------------------------------------------------------------
@ToolRegistry.register(
    name="read_file",
    description="Read the contents of a file. Use this to look up requirement docs, API specs, or saved plans.",
)
def read_file(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return f"ERROR: file not found: {path}"
    try:
        return p.read_text(encoding="utf-8")
    except Exception as e:
        return f"ERROR reading {path}: {e}"


# ------------------------------------------------------------------
# File write tool
# ------------------------------------------------------------------
@ToolRegistry.register(
    name="write_file",
    description="Write content to a file. Use this to save generated plans, intermediate results, etc.",
)
def write_file(path: str, content: str) -> str:
    p = Path(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"OK: wrote {len(content)} bytes to {path}"
    except Exception as e:
        return f"ERROR writing {path}: {e}"


# ------------------------------------------------------------------
# RAG query tool
# ------------------------------------------------------------------
_rag_instance: Optional[Any] = None  # Set by graph node before agent runs


def set_rag_instance(rag):
    global _rag_instance
    _rag_instance = rag


@ToolRegistry.register(
    name="query_knowledge",
    description="Query the RAG knowledge base for best practices, test strategies, and domain rules.",
)
def query_knowledge(query: str, top_n: int = 3) -> str:
    if _rag_instance is None:
        return "ERROR: RAG knowledge base not available."
    try:
        results = _rag_instance.query(query, n_results=top_n)
        if not results:
            return "(no relevant knowledge found)"
        lines = []
        for i, doc in enumerate(results, 1):
            lines.append(f"{i}. {doc}")
        return "\n".join(lines)
    except Exception as e:
        return f"ERROR querying knowledge base: {e}"
