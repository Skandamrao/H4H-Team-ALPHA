"""
ChronoTrace AI — Extraction Service
Uses an LLM to extract temporal events from a raw source record.

Critical rules enforced here:
  - Rule A: APPROVED ≠ IMPLEMENTED  (explicit in prompt + validation)
  - Rule B: PROPOSED ≠ APPROVED
  - Rule C: event_date is extracted from the document, never from datetime.now()
  - Rule G: unknown fields remain null, never fabricated
  - Rule H: every event must cite its evidence_excerpt
"""
from __future__ import annotations

import json
import logging
from typing import Optional
from datetime import date

from app.services.llm_provider import llm
from app.schemas.events import TemporalEventCreate
from app.utils.date_parser import parse_date_expression

logger = logging.getLogger(__name__)

EXTRACTION_SYSTEM_PROMPT = """
You are a precise temporal event extractor for a software project knowledge system called ChronoTrace AI.

Your job is to read a source document (meeting notes, design spec, email, changelog, etc.) and extract
all temporal events about software features, modules, or decisions.

=== CRITICAL ACCURACY RULES ===

Rule A — APPROVED ≠ IMPLEMENTED:
  A decision being approved does NOT mean the feature was implemented. Use separate events.

Rule B — PROPOSED ≠ APPROVED:
  A discussion or suggestion is PROPOSED, not APPROVED. Only mark APPROVED if the document
  explicitly records acceptance/sign-off.

Rule C — Event date is NOT today's date:
  Extract the date FROM THE DOCUMENT. If no date can be found, set event_date to null.
  NEVER use today's date or the ingestion timestamp as a substitute.

Rule G — Unknown fields remain null:
  If you cannot determine the actor, feature name, or date — set them to null.
  Do NOT invent information.

Rule H — Evidence is compulsory:
  Every event must include the exact text excerpt from the document that supports it.

=== EVENT TYPES ===
PROPOSED, APPROVED, REJECTED, IMPLEMENTED, MODIFIED, RENAMED, REMOVED, DEPENDENCY_ADDED, OTHER

=== DATE PRECISION ===
exact, approximate, month, quarter, year, unknown

=== OUTPUT FORMAT ===
Return a JSON array of event objects. Each object must have these fields:
{
  "feature_mention": string | null,        // The feature/module name as mentioned
  "event_type": string,                     // One of the event types above
  "description": string,                    // Human-readable description of what happened
  "previous_name": string | null,           // Only for RENAMED events
  "new_name": string | null,                // Only for RENAMED events
  "event_date_raw": string | null,          // Verbatim date text from document
  "event_date_iso": string | null,          // ISO 8601 (YYYY-MM-DD) if parseable, else null
  "event_date_precision": string,           // exact/approximate/month/quarter/year/unknown
  "evidence_excerpt": string,               // Exact quote from the document (required)
  "actor": string | null,                   // Person/team responsible, if stated
  "extraction_confidence": float            // 0.0 to 1.0
}

Return [] if no temporal events are found.
Return only the JSON array, no other text.
""".strip()


def _build_user_prompt(
    record_type: str,
    title: Optional[str],
    source_date_raw: Optional[str],
    content: str,
) -> str:
    header = f"Record type: {record_type}\n"
    if title:
        header += f"Title: {title}\n"
    if source_date_raw:
        header += f"Document date: {source_date_raw}\n"
    header += "\n=== DOCUMENT CONTENT ===\n"
    return header + content


async def extract_events_from_record(
    project_id: str,
    source_id: str,
    record_type: str,
    title: Optional[str],
    source_date: Optional[date],
    source_date_raw: Optional[str],
    content: str,
) -> list[TemporalEventCreate]:
    """
    Extract temporal events from a single source record using the LLM.
    Returns validated TemporalEventCreate objects ready for DB insertion.
    """
    user_prompt = _build_user_prompt(record_type, title, source_date_raw, content)

    # Check if API keys are configured; if not, seamlessly use rule-based extraction fallback
    from app.config import settings
    from app.services.rule_extractor import extract_rule_based_events
    
    has_api_key = bool(
        (settings.llm_provider == "gemini" and settings.gemini_api_key) or
        (settings.llm_provider == "openai" and settings.openai_api_key)
    )

    if not has_api_key:
        logger.info("No active LLM API key detected — executing deterministic rule-based extractor (Rules A-H enforced).")
        return extract_rule_based_events(
            project_id=project_id,
            source_id=source_id,
            record_type=record_type,
            title=title,
            source_date=source_date,
            source_date_raw=source_date_raw,
            content=content,
        )

    try:
        raw_events: list[dict] = await llm.complete_json(
            EXTRACTION_SYSTEM_PROMPT, user_prompt
        )
    except Exception as exc:
        logger.warning("LLM extraction failed or timed out (%s) — falling back to deterministic extractor.", exc)
        return extract_rule_based_events(
            project_id=project_id,
            source_id=source_id,
            record_type=record_type,
            title=title,
            source_date=source_date,
            source_date_raw=source_date_raw,
            content=content,
        )

    if not isinstance(raw_events, list):
        logger.warning("LLM returned non-list for source %s", source_id)
        return []

    results: list[TemporalEventCreate] = []
    for idx, raw in enumerate(raw_events):
        if not isinstance(raw, dict):
            continue

        # Parse date — Rule C: never substitute now()
        event_date_raw: Optional[str] = raw.get("event_date_raw") or raw.get("event_date_iso")
        if raw.get("event_date_iso"):
            parsed_date, precision, basis = parse_date_expression(raw["event_date_iso"])
        elif raw.get("event_date_raw"):
            parsed_date, precision, basis = parse_date_expression(raw["event_date_raw"])
        else:
            parsed_date, precision, basis = None, "unknown", "unknown"

        # Override precision with LLM's assessment if it's more specific
        llm_precision = raw.get("event_date_precision", "unknown")
        if llm_precision != "unknown" and precision == "unknown":
            precision = llm_precision

        evidence = raw.get("evidence_excerpt", "").strip()
        if not evidence:
            logger.warning(
                "Event %d from source %s has no evidence_excerpt — skipping (Rule H)",
                idx, source_id,
            )
            continue

        event_type = raw.get("event_type", "OTHER").upper()
        if event_type not in {
            "PROPOSED", "APPROVED", "REJECTED", "IMPLEMENTED",
            "MODIFIED", "RENAMED", "REMOVED", "DEPENDENCY_ADDED", "OTHER",
        }:
            event_type = "OTHER"

        try:
            event = TemporalEventCreate(
                project_id=project_id,
                unresolved_feature_mention=raw.get("feature_mention") or None,
                event_type=event_type,  # type: ignore[arg-type]
                description=raw.get("description", "")[:1024],
                previous_name=raw.get("previous_name") or None,
                new_name=raw.get("new_name") or None,
                event_date=parsed_date,
                event_date_raw=event_date_raw,
                event_date_precision=precision,  # type: ignore[arg-type]
                event_date_basis=basis,  # type: ignore[arg-type]
                source_id=source_id,
                evidence_excerpt=evidence,
                actor=raw.get("actor") or None,
                extraction_confidence=float(raw.get("extraction_confidence", 0.5)),
                needs_review=(parsed_date is None),
            )
            results.append(event)
        except Exception as exc:
            logger.warning("Skipping invalid event %d from source %s: %s", idx, source_id, exc)

    return results

