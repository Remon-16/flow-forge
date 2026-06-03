"""Grep-based knowledge search — zero external dependencies.

Replaces the ChromaDB/embedding RAG approach with plain-text keyword search
over .md files in the knowledge directory. Controlled by ENABLE_KNOWLEDGE env var.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)


class KnowledgeSearch:
    """Search knowledge .md files by keyword overlap scoring."""

    def __init__(self, knowledge_dir: str = "./knowledge") -> None:
        self._dir = Path(knowledge_dir)
        if not self._dir.exists():
            logger.warning("Knowledge directory not found: %s", self._dir)

    def search(self, query: str, n_results: int = 3) -> List[str]:
        """Search knowledge files for paragraphs matching the query.

        Returns up to n_results formatted snippets (filename + heading + text).
        Returns empty list if no matches or directory doesn't exist.
        """
        if not self._dir.exists():
            return []

        # Tokenize query into lowercase keywords (len > 1)
        keywords = [kw.lower() for kw in re.split(r"\s+", query.strip()) if len(kw) > 1]
        if not keywords:
            return []

        scored: List[tuple[int, str, str, str]] = []
        for md_file in sorted(self._dir.glob("*.md")):
            try:
                text = md_file.read_text(encoding="utf-8")
            except Exception:
                logger.warning("Cannot read knowledge file: %s", md_file)
                continue

            paragraphs = re.split(r"\n\s*\n", text)
            last_heading = ""

            for para in paragraphs:
                para = para.strip()
                if not para:
                    continue

                # Track headings for context
                heading_match = re.match(r"^#+\s+(.+)", para)
                if heading_match:
                    last_heading = heading_match.group(1).strip()
                    continue

                para_lower = para.lower()
                score = sum(1 for kw in keywords if kw in para_lower)
                if score > 0:
                    truncated = para[:500] + ("..." if len(para) > 500 else "")
                    scored.append((score, md_file.stem, last_heading, truncated))

        scored.sort(key=lambda x: x[0], reverse=True)

        results = []
        for _, stem, heading, snippet in scored[:n_results]:
            context = f"**{stem}**"
            if heading:
                context += f" > {heading}"
            results.append(f"{context}\n{snippet}")

        return results
