"""
ChronoTrace AI — Date Parser
Parses natural-language date expressions from source records.

Critical: NEVER falls back to datetime.utcnow() for an unknown date.
Unknown dates remain None with precision="unknown".
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional, Tuple
from dateutil import parser as du_parser
from dateutil.parser import ParserError


DATE_PRECISION = str   # "exact" | "approximate" | "month" | "quarter" | "year" | "unknown"
DATE_BASIS = str       # "explicit" | "inferred_context" | "inferred_sequence" | "unknown"


# Month name → number
_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9,
    "oct": 10, "nov": 11, "dec": 12,
}


def parse_date_expression(
    raw: Optional[str],
) -> Tuple[Optional[date], DATE_PRECISION, DATE_BASIS]:
    """
    Parse a raw date string from a source record.

    Returns:
        (parsed_date_or_None, precision, basis)

    NEVER returns today's date as a substitute for unknown dates.
    """
    if not raw or not raw.strip():
        return None, "unknown", "unknown"

    text = raw.strip()

    # ── 1. ISO / common numeric formats ──────────────────────────────────────
    iso_match = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", text)
    if iso_match:
        try:
            y, m, d = int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3))
            return date(y, m, d), "exact", "explicit"
        except ValueError:
            pass

    # ── 2. Month + Year  (e.g. "March 2024", "Mar 2024") ────────────────────
    month_year = re.match(
        r"^(january|february|march|april|may|june|july|august|"
        r"september|october|november|december|"
        r"jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)"
        r"[\s,]+(\d{4})$",
        text, re.IGNORECASE,
    )
    if month_year:
        m = _MONTHS[month_year.group(1).lower()]
        y = int(month_year.group(2))
        return date(y, m, 1), "month", "explicit"

    # ── 3. Quarter  (e.g. "Q2 2024", "Q3/2023") ─────────────────────────────
    quarter_match = re.match(r"^Q([1-4])[\s/\-]+(\d{4})$", text, re.IGNORECASE)
    if quarter_match:
        q = int(quarter_match.group(1))
        y = int(quarter_match.group(2))
        first_month = (q - 1) * 3 + 1
        return date(y, first_month, 1), "quarter", "explicit"

    # ── 4. Year only  (e.g. "2023") ──────────────────────────────────────────
    if re.match(r"^\d{4}$", text):
        return date(int(text), 1, 1), "year", "explicit"

    # ── 5. Approximate expressions ───────────────────────────────────────────
    approx_match = re.match(
        r"^(early|mid|late|around|circa|~)\s+(\d{4})$", text, re.IGNORECASE
    )
    if approx_match:
        return date(int(approx_match.group(2)), 1, 1), "approximate", "explicit"

    # ── 6. dateutil fallback (handles "15 Jan 2024", "January 15, 2024", etc.)
    try:
        # dayfirst=False avoids ambiguous swaps; yearfirst=False is default
        parsed = du_parser.parse(text, dayfirst=False, yearfirst=False, fuzzy=False)
        # Reject if dateutil fell back to today's date components
        today = datetime.utcnow().date()
        if parsed.year == today.year and parsed.month == today.month and parsed.day == today.day:
            # Could be a genuine match or a fallback — treat as approximate
            return parsed.date(), "approximate", "inferred_context"
        return parsed.date(), "exact", "explicit"
    except (ParserError, OverflowError, ValueError):
        pass

    # ── 7. Genuinely unparseable — Rule G: return unknown, never fabricate ───
    return None, "unknown", "unknown"


def extract_dates_from_text(text: str) -> list[Tuple[str, date, DATE_PRECISION]]:
    """
    Scan free text for date-like patterns and return (raw_match, parsed_date, precision).
    Used by the extraction service as a pre-pass before LLM processing.
    """
    results: list[Tuple[str, date, DATE_PRECISION]] = []

    # ISO dates
    for m in re.finditer(r"\b(\d{4}-\d{2}-\d{2})\b", text):
        raw = m.group(1)
        parsed, prec, _ = parse_date_expression(raw)
        if parsed:
            results.append((raw, parsed, prec))

    # "Month DD, YYYY" or "DD Month YYYY"
    pattern = (
        r"\b(\d{1,2}\s+(?:january|february|march|april|may|june|july|august|"
        r"september|october|november|december|jan|feb|mar|apr|jun|jul|aug|"
        r"sep|sept|oct|nov|dec)\s+\d{4})\b"
        r"|\b((?:january|february|march|april|may|june|july|august|"
        r"september|october|november|december|jan|feb|mar|apr|jun|jul|aug|"
        r"sep|sept|oct|nov|dec)\s+\d{1,2},?\s+\d{4})\b"
    )
    for m in re.finditer(pattern, text, re.IGNORECASE):
        raw = (m.group(1) or m.group(2)).strip()
        parsed, prec, _ = parse_date_expression(raw)
        if parsed:
            results.append((raw, parsed, prec))

    return results

