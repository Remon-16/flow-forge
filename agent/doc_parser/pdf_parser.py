"""PDF text extraction using pymupdf (fitz)."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class PdfParser:
    """Extract plain text from PDF files for requirement analysis."""

    @staticmethod
    def parse(file_path: str) -> str:
        """Extract all text from a PDF file."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF file not found: {file_path}")

        try:
            import fitz
        except ImportError:
            raise ImportError(
                "pymupdf is required for PDF parsing. "
                "Install with: pip install pymupdf"
            )

        doc = fitz.open(str(path))
        texts: list[str] = []
        for page in doc:
            text = page.get_text()
            if text:
                texts.append(text)
        doc.close()

        result = "\n\n".join(texts)
        logger.info("Extracted %d chars from %d pages in %s",
                    len(result), len(texts), file_path)
        return result
