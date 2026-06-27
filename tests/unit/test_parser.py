import io

import fitz
import pytest
from docx import Document as DocxDocument

from app.core.exceptions import UnsupportedFileTypeError
from app.models.document import DriveFile, SupportedMimeType
from app.services.parser_service import ParserService


# Fixtures 

def make_drive_file(
    name: str = "test.pdf",
    mime: SupportedMimeType = SupportedMimeType.PDF,
) -> DriveFile:
    return DriveFile(id="file-123", name=name, mime_type=mime)


def make_pdf_bytes(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def make_docx_bytes(text: str) -> bytes:
    doc = DocxDocument()
    doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# Tests 

class TestPdfParsing:
    def test_extracts_text_from_valid_pdf(self):
        content = make_pdf_bytes("Hello from a PDF document.")
        file = make_drive_file("sample.pdf", SupportedMimeType.PDF)
        parser = ParserService()

        result = parser.parse(file, content)

        assert "Hello from a PDF document" in result.raw_text
        assert result.char_count > 0
        assert result.extraction_errors == []

    def test_empty_pdf_has_warning(self):
        doc = fitz.open()
        doc.new_page()  # blank page, no text
        buf = io.BytesIO()
        doc.save(buf)
        content = buf.getvalue()

        file = make_drive_file("blank.pdf", SupportedMimeType.PDF)
        parser = ParserService()
        result = parser.parse(file, content)

        assert result.raw_text == ""
        assert len(result.extraction_errors) > 0


class TestDocxParsing:
    def test_extracts_text_from_valid_docx(self):
        content = make_docx_bytes("This is a DOCX document body.")
        file = make_drive_file("sample.docx", SupportedMimeType.DOCX)
        parser = ParserService()

        result = parser.parse(file, content)

        assert "DOCX document body" in result.raw_text
        assert result.char_count > 0

    def test_invalid_docx_content_raises(self):
        file = make_drive_file("corrupt.docx", SupportedMimeType.DOCX)
        parser = ParserService()

        # Pass random bytes as DOCX — should not crash the service
        result = parser.parse(file, b"not a real docx file")
        assert result.extraction_errors  # warnings captured, not raised


class TestTxtParsing:
    def test_extracts_utf8_text(self):
        content = "Plain text content.\nSecond line.".encode("utf-8")
        file = make_drive_file("sample.txt", SupportedMimeType.TXT)
        parser = ParserService()

        result = parser.parse(file, content)

        assert "Plain text content" in result.raw_text
        assert "Second line" in result.raw_text

    def test_latin1_fallback(self):
        content = "Caf\xe9 au lait".encode("latin-1")
        file = make_drive_file("latin.txt", SupportedMimeType.TXT)
        parser = ParserService()

        result = parser.parse(file, content)

        assert "Caf" in result.raw_text
        assert any("latin-1" in e for e in result.extraction_errors)


class TestMdParsing:
    def test_extracts_markdown_text(self):
        content = "# Title\n- Item 1\n- Item 2".encode("utf-8")
        file = make_drive_file("sample.md", SupportedMimeType.MD)
        parser = ParserService()

        result = parser.parse(file, content)

        assert "# Title" in result.raw_text
        assert "Item 1" in result.raw_text
        assert result.extraction_errors == []


class TestCsvParsing:
    def test_extracts_csv_rows(self):
        content = "Header1,Header2\nValue1,Value2\nValue3,Value4".encode("utf-8")
        file = make_drive_file("sample.csv", SupportedMimeType.CSV)
        parser = ParserService()

        result = parser.parse(file, content)

        assert "Header1" in result.raw_text
        assert "Value1" in result.raw_text
        assert "Value2" in result.raw_text
        assert result.extraction_errors == []
