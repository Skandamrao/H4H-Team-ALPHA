"""
ChronoTrace AI — Document Parser & Normalization Engine
Parses real-world multi-format project records:
 - Structured JSON document batches
 - RFC-style email threads (From, To, Date, Subject)
 - Architecture Decision Records (ADR-XXX, Status, Context, Decision)
 - Markdown release notes / changelogs (### New Features, Fixes)
 - Meeting notes (Attendees, Agenda, Action Items)
 - Technical Design Specifications (Overview, Scope, Dependencies)

Strictly obeys Rule C: Missing dates are left as None with unknown precision;
never defaulted to system time.
"""
from __future__ import annotations

import re
import hashlib
from typing import Optional, Dict, Any, List
from datetime import date
from pydantic import BaseModel, Field

from app.utils.date_parser import parse_date_expression


class NormalizedDocument(BaseModel):
    """
    Standardized in-memory representation of an ingested document before DB persistence.
    """
    project_id: str
    record_type: str
    title: Optional[str] = None
    source_date: Optional[date] = None
    source_date_raw: Optional[str] = None
    author: Optional[str] = None
    content: str
    file_reference: Optional[str] = None
    metadata_json: Dict[str, Any] = Field(default_factory=dict)
    content_fingerprint: str = ""

    def compute_fingerprint(self) -> str:
        """
        Deterministic SHA-256 fingerprint for idempotency.
        Includes project_id, record_type, title, source_date_raw, and stripped content.
        Preserves distinct provenance if two identical texts have different dates or authors.
        """
        payload = (
            f"{self.project_id}|{self.record_type}|{self.title or ''}|"
            f"{self.author or ''}|{self.source_date_raw or ''}|{self.content.strip()}"
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_fingerprint(
    project_id: str,
    record_type: str,
    title: Optional[str],
    author: Optional[str],
    source_date_raw: Optional[str],
    content: str,
) -> str:
    payload = (
        f"{project_id}|{record_type}|{title or ''}|"
        f"{author or ''}|{source_date_raw or ''}|{content.strip()}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class DocumentParser:
    """
    Multi-format parser for heterogeneous software project documents.
    """

    @staticmethod
    def parse_email(text: str, project_id: str, file_ref: Optional[str] = None) -> NormalizedDocument:
        """
        Parses RFC-style email threads.
        Looks for From:, To:, Date:, Subject: headers.
        """
        from_match = re.search(r"^From:\s*([^\n\r]+)", text, re.M | re.I)
        date_match = re.search(r"^Date:\s*([^\n\r]+)", text, re.M | re.I)
        subj_match = re.search(r"^Subject:\s*([^\n\r]+)", text, re.M | re.I)
        to_match = re.search(r"^To:\s*([^\n\r]+)", text, re.M | re.I)

        author = from_match.group(1).strip() if from_match else None
        title = subj_match.group(1).strip() if subj_match else "Email Thread"
        raw_date = date_match.group(1).strip() if date_match else None

        parsed_date, _, _ = parse_date_expression(raw_date)

        metadata: Dict[str, Any] = {}
        if to_match:
            metadata["to"] = to_match.group(1).strip()

        # Body is everything after headers if headers exist
        body = text.strip()

        doc = NormalizedDocument(
            project_id=project_id,
            record_type="email_thread",
            title=title,
            source_date=parsed_date,
            source_date_raw=raw_date,
            author=author,
            content=body,
            file_reference=file_ref,
            metadata_json=metadata,
        )
        doc.content_fingerprint = doc.compute_fingerprint()
        return doc

    @staticmethod
    def parse_adr(text: str, project_id: str, file_ref: Optional[str] = None) -> NormalizedDocument:
        """
        Parses Architecture Decision Records (ADRs).
        Looks for ADR number, Status, Date, Decision makers.
        """
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        first_line = lines[0] if lines else "Architecture Decision Record"

        title = first_line.replace("#", "").strip()

        date_match = re.search(r"^Date:\s*([^\n\r]+)", text, re.M | re.I)
        raw_date = date_match.group(1).strip() if date_match else None
        parsed_date, _, _ = parse_date_expression(raw_date)

        makers_match = re.search(r"Decision makers?:\s*([^\n\r]+)", text, re.I)
        author = makers_match.group(1).strip() if makers_match else None

        status_match = re.search(r"Status:\s*([A-Za-z]+)", text, re.I)
        status = status_match.group(1).upper() if status_match else "UNKNOWN"

        metadata = {"adr_status": status}

        doc = NormalizedDocument(
            project_id=project_id,
            record_type="decision_log",
            title=title,
            source_date=parsed_date,
            source_date_raw=raw_date,
            author=author,
            content=text.strip(),
            file_reference=file_ref,
            metadata_json=metadata,
        )
        doc.content_fingerprint = doc.compute_fingerprint()
        return doc

    @staticmethod
    def parse_changelog(text: str, project_id: str, file_ref: Optional[str] = None) -> NormalizedDocument:
        """
        Parses release notes and changelogs.
        """
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        first_line = lines[0] if lines else "Release Notes"
        title = first_line.replace("#", "").strip()

        date_match = re.search(r"Released\s+([A-Za-z0-9,\s]+?)(?:$|\n|\r|—)", text, re.I) or re.search(r"^Date:\s*([^\n\r]+)", text, re.M | re.I)
        raw_date = date_match.group(1).strip() if date_match else None
        parsed_date, _, _ = parse_date_expression(raw_date)

        author_match = re.search(r"^Author:\s*([^\n\r]+)", text, re.M | re.I)
        author = author_match.group(1).strip() if author_match else None

        doc = NormalizedDocument(
            project_id=project_id,
            record_type="changelog",
            title=title,
            source_date=parsed_date,
            source_date_raw=raw_date,
            author=author,
            content=text.strip(),
            file_reference=file_ref,
            metadata_json={},
        )
        doc.content_fingerprint = doc.compute_fingerprint()
        return doc

    @staticmethod
    def parse_meeting_notes(text: str, project_id: str, file_ref: Optional[str] = None) -> NormalizedDocument:
        """
        Parses meeting notes containing Attendees, Agenda, Action items.
        """
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        first_line = lines[0] if lines else "Meeting Notes"
        title = first_line.replace("#", "").strip()

        date_match = re.search(r"(\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b)", text, re.I)
        raw_date = date_match.group(1).strip() if date_match else None
        parsed_date, _, _ = parse_date_expression(raw_date)

        attendees_match = re.search(r"Attendees?:\s*([^\n\r]+)", text, re.I)
        author = None
        metadata: Dict[str, Any] = {}
        if attendees_match:
            attendees = [a.strip() for a in attendees_match.group(1).split(",")]
            author = attendees[0] if attendees else None
            metadata["attendees"] = attendees

        doc = NormalizedDocument(
            project_id=project_id,
            record_type="meeting_notes",
            title=title,
            source_date=parsed_date,
            source_date_raw=raw_date,
            author=author,
            content=text.strip(),
            file_reference=file_ref,
            metadata_json=metadata,
        )
        doc.content_fingerprint = doc.compute_fingerprint()
        return doc

    @classmethod
    def parse_consolidated_transcript(
        cls,
        text: str,
        project_id: str = "proj-alpha",
        file_ref: Optional[str] = "Consolidated_meeting_transcript.txt",
    ) -> List[NormalizedDocument]:
        """
        Parses a multi-meeting consolidated transcript file (e.g. sections marked [Brainstorm meeting 1], [meeting 2], etc.)
        Splits into distinct NormalizedDocument records while preserving provenance and full context.
        """
        # Section headers pattern: [Section Name] at beginning of line
        known_sections = [
            "brainstorm meeting 1", "meeting 2", "meeting 3",
            "rural customer report", "urban customer report",
            "meeting 4", "complain dataset 1", "meeting 5",
            "complain meeting 2", "latest meeting"
        ]

        # Find section positions
        pattern = r"(?m)^\s*\[([^\]]+)\]"
        matches = list(re.finditer(pattern, text))
        
        valid_sections = []
        for m in matches:
            t = m.group(1).strip()
            if any(known in t.lower() for known in known_sections):
                valid_sections.append(m)

        if not valid_sections:
            # Fall back to single document
            return [cls.parse_unstructured_text(text, project_id, file_ref, "Consolidated Meeting Transcript")]

        docs: List[NormalizedDocument] = []
        for i, m in enumerate(valid_sections):
            sec_title = m.group(1).strip()
            start = m.end()
            end = valid_sections[i + 1].start() if i + 1 < len(valid_sections) else len(text)
            sec_content = text[start:end].strip()

            # Determine record_type
            title_lower = sec_title.lower()
            if "report" in title_lower:
                rec_type = "design_spec"
            elif "complain" in title_lower:
                rec_type = "feedback"
            else:
                rec_type = "meeting_notes"

            # Detect primary speaker / chairman
            chairman_match = re.search(r"Meeting Chairman\s*\(([^)]+)\)", sec_content) or re.search(r"^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s*\(", sec_content, re.M)
            author = chairman_match.group(1).strip() if chairman_match else None

            # Look for dates in first 5 lines
            lines = [l.strip() for l in sec_content.split("\n") if l.strip()]
            head = " ".join(lines[:5]) if lines else ""
            date_match = re.search(r"(\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}\b|\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:st|nd|rd|th)?\b)", head, re.I)
            raw_date = date_match.group(1).strip() if date_match else None
            parsed_date, _, _ = parse_date_expression(raw_date)

            doc = NormalizedDocument(
                project_id=project_id,
                record_type=rec_type,
                title=sec_title,
                source_date=parsed_date,
                source_date_raw=raw_date,
                author=author,
                content=sec_content,
                file_reference=file_ref,
                metadata_json={"section_index": i + 1, "section_title": sec_title},
            )
            doc.content_fingerprint = doc.compute_fingerprint()
            docs.append(doc)

        return docs

    @classmethod
    def parse_unstructured_text(
        cls,
        text: str,
        project_id: str = "proj-alpha",
        file_ref: Optional[str] = None,
        suggested_title: Optional[str] = None,
    ) -> NormalizedDocument:
        """
        Auto-detects document type and delegates to the appropriate specialized parser.
        """
        content_lower = text.lower()

        # 1. Email check
        if ("from:" in content_lower and "subject:" in content_lower) or "from: " in content_lower:
            return cls.parse_email(text, project_id, file_ref)

        # 2. ADR check
        if "adr-" in content_lower or "decision makers:" in content_lower or "architecture decision record" in content_lower:
            return cls.parse_adr(text, project_id, file_ref)

        # 3. Changelog / Release notes
        if "release notes" in content_lower or "shipped" in content_lower or "### new features" in content_lower:
            return cls.parse_changelog(text, project_id, file_ref)

        # 4. Meeting notes
        if "attendees:" in content_lower or "sprint planning" in content_lower or "meeting notes" in content_lower:
            return cls.parse_meeting_notes(text, project_id, file_ref)

        # 5. Default generic / other document
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        title = suggested_title or (lines[0].replace("#", "").strip() if lines else "Document")
        
        # Search for any date mention in first 3 lines
        header_text = " ".join(lines[:3]) if lines else ""
        date_match = re.search(r"(\b\d{4}-\d{2}-\d{2}\b|\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b)", header_text, re.I)
        raw_date = date_match.group(1).strip() if date_match else None
        parsed_date, _, _ = parse_date_expression(raw_date)

        doc = NormalizedDocument(
            project_id=project_id,
            record_type="other",
            title=title,
            source_date=parsed_date,
            source_date_raw=raw_date,
            author=None,
            content=text.strip(),
            file_reference=file_ref,
            metadata_json={},
        )
        doc.content_fingerprint = doc.compute_fingerprint()
        return doc

