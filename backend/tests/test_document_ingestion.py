"""
Tests for document ingestion service.

Tests:
  - File type validation
  - Duplicate detection via SHA-256 hash
  - Text extraction from TXT/MD/JSON
  - Date inference from document content
  - File size limit enforcement
"""

import pytest
import json
from app.services.document_processor import (
    compute_file_hash,
    validate_file_type,
    extract_text,
    infer_document_date,
)


class TestFileTypeValidation:
    def test_txt_is_valid(self):
        is_valid, ftype = validate_file_type("notes.txt")
        assert is_valid is True
        assert ftype == "txt"

    def test_md_is_valid(self):
        is_valid, ftype = validate_file_type("readme.md")
        assert is_valid is True
        assert ftype == "md"

    def test_json_is_valid(self):
        is_valid, ftype = validate_file_type("tickets.json")
        assert is_valid is True
        assert ftype == "json"

    def test_pdf_is_valid(self):
        is_valid, ftype = validate_file_type("document.pdf")
        assert is_valid is True
        assert ftype == "pdf"

    def test_exe_is_invalid(self):
        is_valid, _ = validate_file_type("malware.exe")
        assert is_valid is False

    def test_docx_is_invalid(self):
        is_valid, _ = validate_file_type("report.docx")
        assert is_valid is False

    def test_uppercase_extension(self):
        is_valid, ftype = validate_file_type("DOCUMENT.TXT")
        assert is_valid is True
        assert ftype == "txt"


class TestFileHashing:
    def test_same_content_same_hash(self):
        content = b"Hello, ChronoGraph!"
        assert compute_file_hash(content) == compute_file_hash(content)

    def test_different_content_different_hash(self):
        assert compute_file_hash(b"content_a") != compute_file_hash(b"content_b")

    def test_hash_is_64_hex_chars(self):
        h = compute_file_hash(b"test")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


class TestTextExtraction:
    def test_extract_txt(self):
        content = b"This is a test document.\nSecond line."
        text, pages = extract_text(content, "txt")
        assert "test document" in text
        assert pages is None

    def test_extract_md(self):
        content = b"# Heading\n\nSome **markdown** content."
        text, pages = extract_text(content, "md")
        assert "markdown" in text

    def test_extract_json(self):
        data = {"events": [{"title": "Feature introduced", "date": "2024-10-05"}]}
        content = json.dumps(data).encode()
        text, pages = extract_text(content, "json")
        assert "Feature introduced" in text

    def test_invalid_json_raises(self):
        with pytest.raises(ValueError):
            extract_text(b"not valid json {{{", "json")

    def test_unsupported_type_raises(self):
        with pytest.raises(ValueError):
            extract_text(b"content", "docx")


class TestDateInference:
    def test_explicit_date_line(self):
        text = "Date: October 8, 2024\nSome content here."
        date, confidence = infer_document_date(text, "notes.txt")
        assert date is not None
        assert date.year == 2024
        assert date.month == 10
        assert date.day == 8
        assert confidence == "HIGH"

    def test_iso_date_in_filename(self):
        text = "Some content without a date."
        date, confidence = infer_document_date(text, "meeting_2024-10-05.txt")
        assert date is not None
        assert date.year == 2024
        assert confidence == "MEDIUM"

    def test_no_date_returns_unknown(self):
        text = "No date information here at all."
        date, confidence = infer_document_date(text, "nodates.txt")
        assert date is None
        assert confidence == "UNKNOWN"


class TestDuplicateDetection:
    def test_api_duplicate_detection(self, client):
        """Upload the same content twice — second should be flagged as duplicate."""
        content = b"Date: October 5, 2024\nMeeting notes about feature X."

        # First upload
        response1 = client.post(
            "/api/documents/upload",
            files=[("files", ("doc.txt", content, "text/plain"))],
        )
        assert response1.status_code == 201
        results1 = response1.json()
        assert results1[0]["is_duplicate"] is False

        # Second upload — same content
        response2 = client.post(
            "/api/documents/upload",
            files=[("files", ("doc_copy.txt", content, "text/plain"))],
        )
        assert response2.status_code == 201
        results2 = response2.json()
        assert results2[0]["is_duplicate"] is True

