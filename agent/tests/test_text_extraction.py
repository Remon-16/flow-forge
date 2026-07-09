"""Tests for text extraction from doc_parser.text_extractor and doc_parser.pdf_parser.

All external libraries are mocked — NO real PDF/DOCX parsing.
"""

import logging
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from doc_parser.pdf_parser import PdfParser
from doc_parser.text_extractor import extract_text


# ---------------------------------------------------------------------------
# Helper: create a fake fitz module that can be imported
# ---------------------------------------------------------------------------

def _make_fitz_module(pages_data):
    """Return a MagicMock fitz module with open() returning controlled pages.

    *pages_data* is a list of dicts, each with:
        - "text": str — text returned by page.get_text()
        - "images": list — returned by page.get_images() (non-empty means "has images")
    """
    fitz = MagicMock(name="fitz")

    def _mock_page(data):
        page = MagicMock()
        page.get_text.return_value = data.get("text", "")
        page.get_images.return_value = data.get("images", [])
        return page

    pages = [_mock_page(d) for d in pages_data]
    mock_doc = MagicMock()
    mock_doc.__iter__.return_value = iter(pages)
    mock_doc.__enter__ = MagicMock(return_value=mock_doc)
    mock_doc.__exit__ = MagicMock(return_value=False)

    fitz.open.return_value = mock_doc

    return fitz


def _temp_text_file(suffix, content):
    """Write content to a temp file with the given suffix and return its path."""
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=suffix, delete=False, encoding="utf-8",
    )
    tmp.write(content)
    tmp.close()
    return tmp.name


# ---------------------------------------------------------------------------
# extract_text tests
# ---------------------------------------------------------------------------

class TestTextExtraction:
    """Tests for extract_text() with various file formats."""

    def should_extract_text_from_txt_file(self):
        path = _temp_text_file(".txt", "Hello World\nThis is a test.")
        try:
            result = extract_text(path)
            assert result == "Hello World\nThis is a test."
        finally:
            Path(path).unlink(missing_ok=True)

    def should_extract_text_from_md_file(self):
        content = "# Heading\n\nSome **markdown** content."
        path = _temp_text_file(".md", content)
        try:
            result = extract_text(path)
            assert result == content
        finally:
            Path(path).unlink(missing_ok=True)

    def should_extract_text_from_yaml_json_files(self):
        yaml_content = "key: value\nitems:\n  - one\n  - two"
        json_content = '{"key": "value", "items": ["one", "two"]}'

        yaml_path = _temp_text_file(".yaml", yaml_content)
        json_path = _temp_text_file(".json", json_content)
        try:
            assert extract_text(yaml_path) == yaml_content
            assert extract_text(json_path) == json_content
        finally:
            Path(yaml_path).unlink(missing_ok=True)
            Path(json_path).unlink(missing_ok=True)

    def should_extract_text_from_pdf_with_text_layer(self):
        pages = [
            {"text": "Page 1 content", "images": []},
            {"text": "Page 2 content", "images": []},
        ]
        mock_fitz = _make_fitz_module(pages)

        pdf_path = _temp_text_file(".pdf", "dummy")
        try:
            with patch.dict(sys.modules, {"fitz": mock_fitz}):
                result = PdfParser.parse(pdf_path)

            expected = "Page 1 content\n\nPage 2 content"
            assert result == expected
        finally:
            Path(pdf_path).unlink(missing_ok=True)

    def should_warn_on_pdf_with_images_but_little_text(self, caplog):
        pages = [
            {"text": "short", "images": ["img1"]},
        ]
        mock_fitz = _make_fitz_module(pages)

        pdf_path = _temp_text_file(".pdf", "dummy")
        try:
            with patch.dict(sys.modules, {"fitz": mock_fitz}):
                with caplog.at_level(logging.WARNING):
                    result = PdfParser.parse(pdf_path)

            assert result == "short"
            assert any("scanned document" in r.message.lower() or
                       "images with very little extractable text" in r.message.lower()
                       for r in caplog.records)
        finally:
            Path(pdf_path).unlink(missing_ok=True)

    def should_raise_on_binary_file(self):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
            path = tmp.name

        try:
            with pytest.raises(ValueError, match="Unsupported binary format"):
                extract_text(path)
        finally:
            Path(path).unlink(missing_ok=True)

    def should_extract_text_from_docx(self):
        mock_para1 = MagicMock()
        mock_para1.text = "  Paragraph one  "
        mock_para2 = MagicMock()
        mock_para2.text = "Paragraph two"

        mock_cell = MagicMock()
        mock_cell.text = "Cell content"
        mock_row = MagicMock()
        mock_row.cells = [mock_cell]
        mock_table = MagicMock()
        mock_table.rows = [mock_row]

        mock_doc = MagicMock()
        mock_doc.paragraphs = [mock_para1, mock_para2]
        mock_doc.tables = [mock_table]

        mock_docx = MagicMock()
        mock_docx.Document.return_value = mock_doc

        docx_path = _temp_text_file(".docx", "dummy")
        try:
            with patch.dict(sys.modules, {"docx": mock_docx}):
                result = extract_text(docx_path)

            assert "Paragraph one" in result
            assert "Paragraph two" in result
            assert "Cell content" in result
        finally:
            Path(docx_path).unlink(missing_ok=True)

    def should_handle_empty_file(self):
        path = _temp_text_file(".txt", "")
        try:
            result = extract_text(path)
            assert result == ""
        finally:
            Path(path).unlink(missing_ok=True)

    def should_handle_nonexistent_file(self):
        pages = [{"text": "text", "images": []}]
        mock_fitz = _make_fitz_module(pages)

        with patch.dict(sys.modules, {"fitz": mock_fitz}):
            with pytest.raises(FileNotFoundError, match="PDF file not found"):
                PdfParser.parse("/nonexistent/path/file.pdf")
