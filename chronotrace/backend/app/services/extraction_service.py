"""
ChronoTrace AI — Event Extractor Service (P05)
Converts unstructured project records into validated historical event objects without inventing facts.

Key Capabilities:
  - Pluggable LLM Provider abstraction with deterministic fallback
  - Controlled 1-shot self-correction on invalid schema outputs
  - Strict evidence verification with character offset tracking
  - Rules A-H Enforcement:
      Rule A: APPROVED ≠ IMPLEMENTED
      Rule B: PROPOSED ≠ APPROVED
      Rule C: event_date is extracted from the document, never from ingestion timestamp
      Rule G: unknown fields remain None, never fabricated
      Rule H: every event must cite its verbatim evidence_excerpt
"""
from __future__ import annotations

import re
import logging
from typing import Optional, Tuple, Any, List
from datetime import date

from app.services.llm_provider import llm, BaseLLMProvider
from app.schemas.events import TemporalEventCreate
from app.utils.date_parser import parse_date_expression
from app.services.rule_extractor import extract_rule_based_events

logger = logging.getLogger(__name__)

EXTRACTION_SYSTEM_PROMPT = """
You are a precise temporal event extractor for a software project knowledge system called ChronoTrace AI.

Your job is to read a source document (meeting notes, design spec, email, changelog, etc.) and extract
all temporal events about software features, modules, or decisions.

=== CRITICAL ACCURACY RULES ===

Rule A — APPROVED ≠ IMPLEMENTED:
  A decision being approved does NOT mean the feature was implemented. Use separate events.
  Only mark IMPLEMENTED if there is concrete evidence of code shipped, merged, deployed, or live in production.

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

CORRECTION_PROMPT_TEMPLATE = """
Your previous extraction JSON array was rejected due to schema or validation errors:
{validation_error}

Previous JSON output:
{previous_raw}

Original Document Content:
{document_content}

Please correct the output so every object strictly conforms to the JSON format and rules:
1. Every event must include an exact verbatim evidence_excerpt from the document.
2. If event_type is RENAMED, both previous_name and new_name must be non-null strings.
3. If no implementation proof exists, do not use IMPLEMENTED.
Return ONLY the corrected JSON array.
""".strip()


class EventExtractor:
    """
    Evidence-grounded temporal event extraction service for ChronoTrace AI.
    Converts unstructured project records into validated historical event objects without hallucination.
    """

    def __init__(self, provider: Optional[Any] = None) -> None:
        self.provider = provider or llm

    @staticmethod
    def verify_evidence(content: str, evidence: str) -> Tuple[bool, Optional[int], Optional[int]]:
        """
        Verify that evidence_excerpt corresponds verbatim to actual source content.
        Returns (is_verbatim, start_offset, end_offset).
        A paraphrase must not be presented as a verbatim quote (Rule H & P05 Requirement F).
        """
        if not evidence or not evidence.strip():
            return False, None, None

        stripped_ev = evidence.strip()
        pos = content.find(stripped_ev)
        if pos != -1:
            return True, pos, pos + len(stripped_ev)

        # Try whitespace normalized lookup
        norm_content = re.sub(r"\s+", " ", content)
        norm_ev = re.sub(r"\s+", " ", stripped_ev)
        norm_pos = norm_content.find(norm_ev)
        if norm_pos != -1:
            return True, norm_pos, norm_pos + len(norm_ev)

        # Evidence is a paraphrase or altered quote
        return False, None, None

    async def _execute_with_correction(
        self,
        system_prompt: str,
        user_prompt: str,
        document_content: str,
    ) -> list[dict]:
        """
        Execute LLM call with exactly ONE controlled structured-output correction attempt if invalid.
        (Requirement E: Controlled self-correction, do not indefinitely retry).
        """
        try:
            raw_response = await self.provider.complete_json(system_prompt, user_prompt)
            if isinstance(raw_response, list):
                return raw_response
            error_msg = f"Expected JSON list but got {type(raw_response).__name__}"
        except Exception as exc:
            error_msg = str(exc)
            raw_response = str(exc)

        # Attempt 1 controlled structured-output correction
        logger.warning("LLM extraction failed validation (%s). Attempting 1 controlled self-correction...", error_msg)
        try:
            correction_user_prompt = CORRECTION_PROMPT_TEMPLATE.format(
                validation_error=error_msg,
                previous_raw=str(raw_response)[:1000],
                document_content=document_content[:2000],
            )
            corrected_response = await self.provider.complete_json(
                system_prompt, correction_user_prompt
            )
            if isinstance(corrected_response, list):
                logger.info("Controlled self-correction succeeded.")
                return corrected_response
        except Exception as retry_exc:
            logger.warning("Controlled self-correction attempt also failed: %s", retry_exc)

        # Preserve original source, return empty so pipeline falls back to deterministic extractor
        return []

    async def extract_events(
        self,
        project_id: str,
        source_id: str,
        record_type: str,
        title: Optional[str],
        source_date: Optional[date],
        source_date_raw: Optional[str],
        content: str,
    ) -> List[TemporalEventCreate]:
        """
        Extract atomic temporal events from a source document.
        Validates output against Pydantic schema and source evidence bounds.
        """
        from app.config import settings
        from app.services.llm_provider import LLMProvider

        is_custom_provider = self.provider is not None and not isinstance(self.provider, LLMProvider)
        has_api_key = is_custom_provider or bool(
            (settings.llm_provider == "gemini" and settings.gemini_api_key and settings.gemini_api_key != "test-key") or
            (settings.llm_provider == "openai" and settings.openai_api_key and settings.openai_api_key != "test-key") or
            (settings.llm_provider == "mock")
        )

        if not has_api_key:
            logger.info("Executing deterministic rule-based extractor (Rules A-H enforced).")
            return self._enrich_rule_based_offsets(
                extract_rule_based_events(
                    project_id=project_id,
                    source_id=source_id,
                    record_type=record_type,
                    title=title,
                    source_date=source_date,
                    source_date_raw=source_date_raw,
                    content=content,
                ),
                content,
            )

        header = f"Record type: {record_type}\n"
        if title:
            header += f"Title: {title}\n"
        if source_date_raw:
            header += f"Document date: {source_date_raw}\n"
        header += "\n=== DOCUMENT CONTENT ===\n"
        user_prompt = header + content

        raw_events = await self._execute_with_correction(
            system_prompt=EXTRACTION_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            document_content=content,
        )

        if not raw_events:
            logger.info("Falling back to deterministic rule extractor for source %s", source_id)
            return self._enrich_rule_based_offsets(
                extract_rule_based_events(
                    project_id=project_id,
                    source_id=source_id,
                    record_type=record_type,
                    title=title,
                    source_date=source_date,
                    source_date_raw=source_date_raw,
                    content=content,
                ),
                content,
            )

        results: List[TemporalEventCreate] = []
        for idx, raw in enumerate(raw_events):
            if not isinstance(raw, dict):
                continue

            evidence = str(raw.get("evidence_excerpt") or "").strip()
            if not evidence:
                logger.warning("Event %d from source %s missing evidence_excerpt (Rule H) — skipping", idx, source_id)
                continue

            # Verify verbatim evidence & compute stable character offsets (Requirement F)
            is_verbatim, start_offset, end_offset = self.verify_evidence(content, evidence)

            # Date extraction — Rule C: never substitute now()
            event_date_raw: Optional[str] = raw.get("event_date_raw") or raw.get("event_date_iso")
            if raw.get("event_date_iso"):
                parsed_date, precision, basis = parse_date_expression(raw["event_date_iso"])
            elif raw.get("event_date_raw"):
                parsed_date, precision, basis = parse_date_expression(raw["event_date_raw"])
            elif source_date:
                parsed_date, precision, basis = source_date, "exact", "inferred_context"
            else:
                parsed_date, precision, basis = None, "unknown", "unknown"

            llm_precision = raw.get("event_date_precision", "unknown")
            if llm_precision != "unknown" and precision == "unknown":
                precision = llm_precision

            event_type = str(raw.get("event_type", "OTHER")).upper()
            if event_type not in {
                "PROPOSED", "APPROVED", "REJECTED", "IMPLEMENTED",
                "MODIFIED", "RENAMED", "REMOVED", "DEPENDENCY_ADDED", "OTHER",
            }:
                event_type = "OTHER"

            # Rule A & Rule B Sanity Corrections
            evidence_lower = evidence.lower()
            if event_type == "IMPLEMENTED" and any(
                phrase in evidence_lower for phrase in [
                    "no implementation", "approval only", "never implemented",
                    "not shipped", "still not approved", "pending"
                ]
            ):
                event_type = "APPROVED" if "approved" in evidence_lower else "OTHER"

            if event_type == "APPROVED" and any(
                phrase in evidence_lower for phrase in ["no decision made", "not approved", "pending review"]
            ):
                event_type = "PROPOSED"

            confidence = float(raw.get("extraction_confidence", 0.8))
            needs_review = bool(
                parsed_date is None or
                not is_verbatim or
                confidence < 0.6
            )

            try:
                event = TemporalEventCreate(
                    project_id=project_id,
                    unresolved_feature_mention=raw.get("feature_mention") or None,
                    event_type=event_type,  # type: ignore[arg-type]
                    description=str(raw.get("description", ""))[:1024],
                    previous_name=raw.get("previous_name") or None,
                    new_name=raw.get("new_name") or None,
                    event_date=parsed_date,
                    event_date_raw=event_date_raw,
                    event_date_precision=precision,  # type: ignore[arg-type]
                    event_date_basis=basis,  # type: ignore[arg-type]
                    source_id=source_id,
                    evidence_excerpt=evidence,
                    evidence_offset_start=start_offset,
                    evidence_offset_end=end_offset,
                    actor=raw.get("actor") or None,
                    extraction_confidence=confidence,
                    needs_review=needs_review,
                )
                results.append(event)
            except Exception as exc:
                logger.warning("Event %d failed schema validation: %s", idx, exc)

        return results

    @staticmethod
    def _enrich_rule_based_offsets(events: List[TemporalEventCreate], content: str) -> List[TemporalEventCreate]:
        """Calculates exact character offsets for deterministic rule-based extractions."""
        for ev in events:
            if ev.evidence_excerpt:
                pos = content.find(ev.evidence_excerpt.strip())
                if pos != -1:
                    ev.evidence_offset_start = pos
                    ev.evidence_offset_end = pos + len(ev.evidence_excerpt.strip())
        return events


# Delegating function for existing calls
async def extract_events_from_record(
    project_id: str,
    source_id: str,
    record_type: str,
    title: Optional[str],
    source_date: Optional[date],
    source_date_raw: Optional[str],
    content: str,
) -> list[TemporalEventCreate]:
    extractor = EventExtractor()
    return await extractor.extract_events(
        project_id=project_id,
        source_id=source_id,
        record_type=record_type,
        title=title,
        source_date=source_date,
        source_date_raw=source_date_raw,
        content=content,
    )
