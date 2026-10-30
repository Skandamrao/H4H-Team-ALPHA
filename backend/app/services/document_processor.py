"""
Document Ingestion Service.

Handles text extraction from PDF, TXT, Markdown and JSON files.
Computes SHA-256 hash for duplicate detection.
Extracts document dates where possible.
Never confuses document date with ingestion date.
"""

import hashlib
import json
import logging
import os
import re
from datetime import datetime
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Supported MIME types mapped to file type labels
SUPPORTED_TYPES = {
    "pdf": "pdf",
    "txt": "txt",
    "md": "md",
    "markdown": "md",
    "json": "json",
}

# Simple date patterns to search for in plain-text documents
_DATE_PATTERNS = [
    # 2024-10-08
    (re.compile(r"\b(\d{4}-\d{2}-\d{2})\b"), "%Y-%m-%d"),
    # October 8, 2024 | Oct 8, 2024
    (re.compile(r"\b((?:January|February|March|April|May|June|July|August|September|October|November|December|"
                r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+\d{1,2},?\s+\d{4})\b"), None),
    # 08/10/2024
    (re.compile(r"\b(\d{2}/\d{2}/\d{4})\b"), "%d/%m/%Y"),
]


def compute_file_hash(file_bytes: bytes) -> str:
    """Return the SHA-256 hex digest of *file_bytes*."""
    return hashlib.sha256(file_bytes).hexdigest()


def get_file_extension(filename: str) -> str:
    """Extract and normalise the file extension."""
    ext = os.path.splitext(filename)[1].lstrip(".").lower()
    return ext


def validate_file_type(filename: str) -> Tuple[bool, str]:
    """Return (is_valid, file_type_label)."""
    ext = get_file_extension(filename)
    if ext in SUPPORTED_TYPES:
        return True, SUPPORTED_TYPES[ext]
    return False, ext


def extract_text_from_pdf(file_bytes: bytes) -> Tuple[str, int]:
    """Extract plain text from a PDF using PyMuPDF. Returns (text, page_count)."""
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(stream=file_bytes, filetype="pdf")
        pages = [page.get_text() for page in doc]
        doc.close()
        return "\n".join(pages), len(pages)
    except ImportError:
        logger.warning("PyMuPDF not installed — cannot extract PDF text.")
        return "", 0
    except Exception as exc:
        logger.error("PDF extraction failed: %s", exc)
        raise


def extract_text_from_txt(file_bytes: bytes) -> str:
    """Decode plain-text or Markdown file."""
    for encoding in ("utf-8", "latin-1", "cp1252"):
        try:
            return file_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    return file_bytes.decode("utf-8", errors="replace")


def extract_text_from_json(file_bytes: bytes) -> str:
    """Parse JSON and return a pretty-printed string for downstream processing."""
    try:
        data = json.loads(file_bytes.decode("utf-8"))
        return json.dumps(data, indent=2, ensure_ascii=False)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.error("JSON parsing failed: %s", exc)
        raise ValueError(f"Invalid JSON file: {exc}") from exc


def extract_text(file_bytes: bytes, file_type: str) -> Tuple[str, Optional[int]]:
    """Dispatch to the appropriate extractor. Returns (text, page_count_or_None)."""
    if file_type == "pdf":
        text, pages = extract_text_from_pdf(file_bytes)
        return text, pages
    elif file_type in ("txt", "md"):
        return extract_text_from_txt(file_bytes), None
    elif file_type == "json":
        return extract_text_from_json(file_bytes), None
    else:
        raise ValueError(f"Unsupported file type: {file_type}")


def _try_parse_date(raw: str) -> Optional[datetime]:
    """Attempt to parse a raw date string into a datetime."""
    formats = [
        "%Y-%m-%d",
        "%B %d, %Y",
        "%B %d %Y",
        "%b %d, %Y",
        "%b %d %Y",
        "%d/%m/%Y",
        "%m/%d/%Y",
    ]
    cleaned = raw.strip().rstrip(",").replace("  ", " ")
    for fmt in formats:
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    return None


def infer_document_date(text: str, filename: str) -> Tuple[Optional[datetime], str]:
    """
    Attempt to infer the document's creation date from its content.

    Returns (date, confidence) where confidence is HIGH | MEDIUM | LOW | UNKNOWN.
    We never invent a date — if we cannot find one, we return (None, 'UNKNOWN').
    """
    # 1. Look for explicit "Date: …" lines near the top of the document
    top_text = text[:2000]
    date_line_match = re.search(
        r"(?:Date|Created|Written|Meeting Date|Record Date)\s*[:：]\s*(.+)", top_text, re.IGNORECASE
    )
    if date_line_match:
        parsed = _try_parse_date(date_line_match.group(1))
        if parsed:
            return parsed, "HIGH"

    # 2. Look for ISO dates in the filename (e.g. "meeting_2024-10-08.pdf")
    filename_match = re.search(r"(\d{4}-\d{2}-\d{2})", filename)
    if filename_match:
        parsed = _try_parse_date(filename_match.group(1))
        if parsed:
            return parsed, "MEDIUM"

    # 3. Scan the first 3000 characters for any recognisable date pattern
    for pattern, fmt in _DATE_PATTERNS:
        match = pattern.search(top_text)
        if match:
            parsed = _try_parse_date(match.group(1))
            if parsed:
                return parsed, "LOW"

    return None, "UNKNOWN"

