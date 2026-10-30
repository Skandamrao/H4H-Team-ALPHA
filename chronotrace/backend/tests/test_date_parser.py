"""
Tests for the date parser utility.
Rule C: event_date NEVER defaults to today's date.
"""
import pytest
from datetime import date
from app.utils.date_parser import parse_date_expression


def test_iso_date():
    d, prec, basis = parse_date_expression("2024-01-15")
    assert d == date(2024, 1, 15)
    assert prec == "exact"
    assert basis == "explicit"


def test_month_year():
    d, prec, basis = parse_date_expression("March 2024")
    assert d == date(2024, 3, 1)
    assert prec == "month"


def test_quarter():
    d, prec, basis = parse_date_expression("Q2 2024")
    assert d == date(2024, 4, 1)
    assert prec == "quarter"


def test_year_only():
    d, prec, basis = parse_date_expression("2023")
    assert d == date(2023, 1, 1)
    assert prec == "year"


def test_approximate():
    d, prec, basis = parse_date_expression("early 2024")
    assert d == date(2024, 1, 1)
    assert prec == "approximate"


def test_none_input():
    """Rule G: None input stays None — never fabricated."""
    d, prec, basis = parse_date_expression(None)
    assert d is None
    assert prec == "unknown"


def test_empty_string():
    """Rule G: Empty string → unknown, not today."""
    d, prec, basis = parse_date_expression("")
    assert d is None
    assert prec == "unknown"


def test_unparseable():
    """Rule G: Unparseable text stays None."""
    d, prec, basis = parse_date_expression("sometime last year")
    assert d is None
    assert prec == "unknown"


def test_natural_date():
    d, prec, basis = parse_date_expression("January 10, 2024")
    assert d == date(2024, 1, 10)
    assert prec == "exact"


def test_no_today_fallback():
    """Critical Rule C test: parser must never return today's date for unknown input."""
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).date()
    d, prec, _ = parse_date_expression("not a date at all xyz")
    # If it returned today, it silently violated Rule C
    assert d is None, f"Parser returned {d} (today={today}); should return None for unknown dates"

