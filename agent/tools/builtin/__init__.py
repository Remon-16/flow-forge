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
# Grep knowledge search tool
# ------------------------------------------------------------------
_knowledge_instance: Optional[Any] = None  # Set by graph node before agent runs


def set_knowledge_instance(knowledge):
    global _knowledge_instance
    _knowledge_instance = knowledge


@ToolRegistry.register(
    name="grep_knowledge",
    description="Search the test knowledge base (.md files) for best practices, "
                "test strategies, business rules, and domain patterns. "
                "Use this when you need reference information for test case design.",
)
def grep_knowledge(query: str, top_n: int = 3) -> str:
    if _knowledge_instance is None:
        return "ERROR: Knowledge base not available (ENABLE_KNOWLEDGE is off)."
    try:
        results = _knowledge_instance.search(query, n_results=top_n)
        if not results:
            return "(no relevant knowledge found)"
        lines = []
        for i, doc in enumerate(results, 1):
            lines.append(f"{i}. {doc}")
        return "\n".join(lines)
    except Exception as e:
        return f"ERROR searching knowledge base: {e}"
