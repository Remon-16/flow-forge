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
        has_images = False
        for page in doc:
            text = page.get_text()
            if text:
                texts.append(text)
            if not has_images and page.get_images():
                has_images = True
        doc.close()

        result = "\n\n".join(texts)

        if has_images and len(result) < 100:
            logger.warning(
                "PDF '%s' contains images with very little extractable text (%d chars). "
                "This may be a scanned document — image content will NOT be processed. "
                "Consider OCR or providing a text-based version.",
                file_path, len(result),
            )
        elif has_images:
            logger.info(
                "PDF '%s' contains embedded images. Only text layer was extracted; "
                "content inside images (screenshots, diagrams) will NOT be processed.",
                file_path,
            )

        logger.info("Extracted %d chars from %d pages in %s",
                    len(result), len(texts), file_path)
        return result
