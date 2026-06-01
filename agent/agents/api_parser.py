"""ApiParser: parse OpenAPI or Markdown API docs into InterfaceDef list."""

import logging
from pathlib import Path
from typing import List

from models.schema import InterfaceDef
from doc_parser.openapi_parser import OpenApiParser
from doc_parser.markdown_parser import MarkdownParser

logger = logging.getLogger(__name__)

_OPENAPI_EXTENSIONS = {".yaml", ".yml", ".json"}
_MARKDOWN_EXTENSIONS = {".md", ".markdown"}


class ApiParser:
    """Parse API documentation from OpenAPI spec or Markdown tables.

    Auto-detects file format based on extension.
    """

    @staticmethod
    def parse(file_path: str) -> List[InterfaceDef]:
        """Parse API doc file and return a list of InterfaceDef."""
        suffix = Path(file_path).suffix.lower()

        if suffix in _OPENAPI_EXTENSIONS:
            logger.info("Parsing OpenAPI spec: %s", file_path)
            return OpenApiParser.parse(file_path)

        if suffix in _MARKDOWN_EXTENSIONS:
            logger.info("Parsing Markdown API doc: %s", file_path)
            return MarkdownParser.parse(file_path)

        # Try OpenAPI first, fall back to markdown
        try:
            return OpenApiParser.parse(file_path)
        except Exception:
            logger.info("OpenAPI parse failed, trying Markdown: %s", file_path)
            return MarkdownParser.parse(file_path)
