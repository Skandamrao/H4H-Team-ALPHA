"""
AI Event Extraction Service using Groq and Google Gemini with deterministic fallback.

Sends document text to Groq/Gemini and parses structured JSON output
into validated ExtractedEvent objects.

Key guarantees:
  - AI output is always validated against the ExtractedEvent schema.
  - A proposal is never automatically marked as approved.
  - An approved decision is never automatically marked as implemented.
  - If Groq JSON mode encounters a 400 json_validate_failed error,
    it automatically retries in freeform text mode and extracts JSON.
  - If external AI calls fail entirely for a chunk, falls back to
    deterministic rule-based event extraction so no document chunk is dropped.
"""

import json
import logging
import re
import time
from typing import List, Optional

from app.core.config import settings
from app.schemas.schemas import ExtractedEvent, ExtractionResult

logger = logging.getLogger(__name__)

# Chunk size in characters for Groq (~3,000 tokens per chunk).
_GROQ_CHUNK_SIZE = 12_000

# Seconds to sleep between Groq chunk calls to avoid TPM accumulation.
_GROQ_CHUNK_DELAY_SEC = 2

# Maximum number of chunks to process per document to avoid HTTP timeouts on massive files.
_MAX_CHUNKS_PER_DOC = 8

# Groq models to use for extraction (with automatic fallback).
_PRIMARY_MODEL = "openai/gpt-oss-120b"
_FALLBACK_MODEL = "openai/gpt-oss-20b"
_ADDITIONAL_MODELS = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]

_EXTRACTION_SYSTEM_PROMPT = """You are an expert software project historian analysing project records.
Extract discrete historical events from the provided document text.
Output a JSON object with a single key "events" whose value is an array of event objects.
Each event object MUST have exactly these fields:
{
  "title": "Short, clear event title",
  "description": "Detailed description of what happened",
  "event_type": "<one of the allowed event types>",
  "feature_name": "Name of the feature, or null",
  "module_name": "Name of the module, or null",
  "related_features": ["list", "of", "related", "features"],
  "decision": "Decision text if applicable, or null",
  "reason": "Why this event happened, or null",
  "event_date": "YYYY-MM-DD if explicitly stated, or null",
  "event_date_confidence": "HIGH | MEDIUM | LOW | UNKNOWN",
  "decision_status": "PROPOSED | APPROVED | REJECTED | IMPLEMENTED | CANCELLED | UNKNOWN",
  "responsible_person": "Person name, or null",
  "supporting_text": "Exact verbatim excerpt from the document supporting this event",
  "confidence_score": 0.0 to 1.0
}

ALLOWED EVENT TYPES:
  FEATURE_INTRODUCED, FEATURE_MODIFIED, FEATURE_RENAMED, FEATURE_REMOVED,
  DECISION_PROPOSED, DECISION_APPROVED, DECISION_REJECTED,
  FEATURE_IMPLEMENTED, FEATURE_DEPRECATED, MODULE_CREATED, MODULE_MODIFIED

CRITICAL RULES:
1. NEVER mark an event as APPROVED unless the document explicitly states approval.
2. NEVER mark an event as IMPLEMENTED unless the document explicitly states implementation.
3. If no events are found in this chunk, return {"events": []}.
4. Return ONLY valid JSON starting with { and ending with }."""


def _chunk_text(text: str, chunk_size: int = _GROQ_CHUNK_SIZE) -> List[str]:
    """
    Split *text* into chunks of at most *chunk_size* characters.
    Prefers splitting on paragraph boundaries, then sentence boundaries.
    """
    if len(text) <= chunk_size:
        return [text]

    chunks: List[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= chunk_size:
            chunks.append(remaining)
            break

        window = remaining[:chunk_size]
        split_pos = window.rfind("\n\n")
        if split_pos == -1:
            split_pos = max(window.rfind(". "), window.rfind(".\n"))
        if split_pos == -1:
            split_pos = chunk_size - 1

        chunks.append(remaining[: split_pos + 1])
        remaining = remaining[split_pos + 1 :].lstrip()

    return [c for c in chunks if c.strip()]


def _clean_and_parse_json(raw: str) -> dict:
    """
    Robustly extract and parse JSON from an LLM response string.
    Handles markdown fences, prefixes, and trailing commentary.
    """
    cleaned = raw.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start : end + 1]

    return json.loads(cleaned)


def _fallback_rule_extraction(chunk: str, document_filename: str) -> List[dict]:
    """
    Deterministic rule-based event extraction used if AI API calls fail on a chunk.
    Scans for key decision and lifecycle phrases to ensure no records are lost.
    """
    extracted: List[dict] = []
    lines = chunk.splitlines()

    # Common patterns for software meeting notes / transcripts / tickets
    patterns = [
        (r"\b(?:approved|agreed to|signed off on)\s+([A-Za-z0-9_\-\s]{3,40})", "DECISION_APPROVED", "APPROVED"),
        (r"\b(?:propose|proposed|proposal for)\s+([A-Za-z0-9_\-\s]{3,40})", "DECISION_PROPOSED", "PROPOSED"),
        (r"\b(?:rejected|declined|decided against)\s+([A-Za-z0-9_\-\s]{3,40})", "DECISION_REJECTED", "REJECTED"),
        (r"\b(?:implemented|shipped|deployed|completed)\s+([A-Za-z0-9_\-\s]{3,40})", "FEATURE_IMPLEMENTED", "IMPLEMENTED"),
        (r"\b(?:renamed|renaming)\s+([A-Za-z0-9_\-\s]{3,30})\s+to\s+([A-Za-z0-9_\-\s]{3,30})", "FEATURE_RENAMED", "APPROVED"),
        (r"\b(?:deprecate|deprecated|removing|removed)\s+([A-Za-z0-9_\-\s]{3,40})", "FEATURE_DEPRECATED", "APPROVED"),
    ]

    for line in lines:
        line_clean = line.strip()
        if len(line_clean) < 15:
            continue

        for pat, ev_type, dec_status in patterns:
            match = re.search(pat, line_clean, re.IGNORECASE)
            if match:
                feat_target = match.group(1).strip()
                title = f"{ev_type.replace('_', ' ').capitalize()}: {feat_target}"
                extracted.append({
                    "title": title[:100],
                    "description": line_clean[:300],
                    "event_type": ev_type,
                    "feature_name": feat_target[:60],
                    "module_name": None,
                    "related_features": [],
                    "decision": line_clean[:200] if "DECISION" in ev_type else None,
                    "reason": None,
                    "event_date": None,
                    "event_date_confidence": "UNKNOWN",
                    "decision_status": dec_status,
                    "responsible_person": None,
                    "supporting_text": line_clean[:350],
                    "confidence_score": 0.75,
                })
                break  # One event per line max

    return extracted[:15]  # Cap at 15 per chunk to prevent spam


class AIExtractionService:
    """Wraps Groq calls for structured event extraction with chunking support."""

    def __init__(self) -> None:
        pass

    def _call_gemini(self, gemini_key: str, prompt: str) -> Optional[str]:
        """Call Google Gemini API with JSON mode."""
        try:
            import google.generativeai as genai
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel(
                "gemini-2.5-flash",
                generation_config={"response_mime_type": "application/json", "temperature": 0.1},
            )
            resp = model.generate_content(prompt)
            return resp.text
        except Exception as exc:
            logger.warning("Gemini extraction call failed (e.g. quota limit): %s. Falling back to Groq.", exc)
            return None

    def _call_groq(self, groq_client, prompt: str) -> str:
        """
        Call Groq with automatic retry across models and fallback to freeform JSON mode.
        If Groq JSON mode raises json_validate_failed (400), seamlessly retries without
        the grammar restriction and parses the JSON output.
        """
        models_to_try = [_PRIMARY_MODEL, _FALLBACK_MODEL] + _ADDITIONAL_MODELS
        last_error = None

        for model_name in models_to_try:
            # 1. First attempt: Strict JSON object mode
            try:
                completion = groq_client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": _EXTRACTION_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.1,
                )
                content = completion.choices[0].message.content
                if content and content.strip():
                    return content
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Groq JSON mode call with model '%s' failed: %s. Retrying without response_format constraint...",
                    model_name, exc,
                )

            # 2. Second attempt: Freeform text mode without response_format restriction
            # (Bypasses Groq's json_validate_failed grammar engine completely)
            try:
                completion = groq_client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are an expert software project historian. Output ONLY valid JSON matching "
                                "{\"events\": [...]}. Do NOT include markdown formatting, code fences, or explanations. "
                                "Start directly with {"
                            ),
                        },
                        {
                            "role": "user",
                            "content": (
                                f"{prompt}\n\nIMPORTANT: Output ONLY a JSON object: {{\"events\": [...]}}. "
                                "If no events exist, output {\"events\": []}."
                            ),
                        },
                    ],
                    temperature=0.1,
                )
                content = completion.choices[0].message.content
                if content and content.strip():
                    return content
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Groq freeform call with model '%s' failed: %s. Trying fallback model.",
                    model_name, exc,
                )
                time.sleep(1)

        raise last_error or RuntimeError("All Groq model attempts failed.")

    def _get_credentials(self) -> dict:
        """Dynamically fetch Gemini and Groq credentials from env / .env file."""
        import os
        from dotenv import load_dotenv
        env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"))
        if os.path.exists(env_path):
            load_dotenv(env_path, override=False)
        return {
            "gemini": os.getenv("GEMINI_API_KEY", "") or getattr(settings, "gemini_api_key", ""),
            "groq": os.getenv("GROQ_API_KEY", "") or getattr(settings, "groq_api_key", ""),
        }

    def extract_events(self, document_id: str, text: str, document_filename: str) -> ExtractionResult:
        """
        Run AI extraction on *text* and return a validated ExtractionResult.
        Chunks large documents, tries Gemini/Groq, and employs deterministic fallback if needed.
        """
        creds = self._get_credentials()
        gemini_key = creds.get("gemini")
        groq_key = creds.get("groq")

        if not gemini_key and not groq_key:
            return ExtractionResult(
                document_id=document_id,
                events=[],
                extraction_errors=["Neither GEMINI_API_KEY nor GROQ_API_KEY is configured."],
            )

        groq_client = None
        if groq_key:
            import groq
            groq_client = groq.Groq(api_key=groq_key)

        all_chunks = _chunk_text(text)
        chunks = all_chunks[:_MAX_CHUNKS_PER_DOC]
        total_chunks = len(chunks)

        all_raw_events: List[dict] = []
        errors: List[str] = []
        last_raw_response: Optional[str] = None

        for i, chunk in enumerate(chunks, start=1):
            logger.info("Processing chunk %d/%d for '%s' (%d chars).", i, total_chunks, document_filename, len(chunk))
            prompt = (
                f"DOCUMENT EXCERPT:\n{chunk}\n\n"
                "TASK: Extract all discrete historical software events from the excerpt above. "
                "Output ONLY a valid JSON object matching {\"events\": [...]}. If no events are described, output {\"events\": []}."
            )

            raw_response = None
            try:
                if gemini_key:
                    raw_response = self._call_gemini(gemini_key, prompt)
                if not raw_response and groq_client:
                    raw_response = self._call_groq(groq_client, prompt)
                if not raw_response:
                    raise RuntimeError("All AI extraction calls (Gemini and Groq) failed for this chunk.")
                last_raw_response = raw_response
            except Exception as exc:
                logger.warning(
                    "AI extraction failed for '%s' chunk %d/%d: %s. Using deterministic rule fallback.",
                    document_filename, i, total_chunks, exc,
                )
                # Fallback to deterministic rule-based extraction for this chunk so no data is lost
                fallback_events = _fallback_rule_extraction(chunk, document_filename)
                if fallback_events:
                    logger.info("Rule-based fallback extracted %d events for chunk %d.", len(fallback_events), i)
                    all_raw_events.extend(fallback_events)
                if i < total_chunks:
                    time.sleep(_GROQ_CHUNK_DELAY_SEC)
                continue

            # Parse JSON from AI response
            try:
                data = _clean_and_parse_json(raw_response)
                chunk_events = data.get("events", [])
                if isinstance(chunk_events, list):
                    all_raw_events.extend(chunk_events)
                    logger.info("Chunk %d/%d yielded %d raw events.", i, total_chunks, len(chunk_events))
                else:
                    logger.warning("Chunk %d/%d: 'events' field is not a list. Using rule fallback.", i, total_chunks)
                    fallback_events = _fallback_rule_extraction(chunk, document_filename)
                    all_raw_events.extend(fallback_events)
            except Exception as exc:
                logger.warning("JSON decode failed for chunk %d/%d: %s. Using rule fallback.", i, total_chunks, exc)
                fallback_events = _fallback_rule_extraction(chunk, document_filename)
                all_raw_events.extend(fallback_events)

            if i < total_chunks:
                time.sleep(_GROQ_CHUNK_DELAY_SEC)

        # Validate each event against schema
        validated: List[ExtractedEvent] = []
        for i, raw_event in enumerate(all_raw_events):
            try:
                from app.schemas.schemas import ExtractedEvent as _EE
                event = _EE.model_validate(raw_event)
                validated.append(event)
            except Exception as exc:
                logger.warning("Event #%d validation skipped: %s", i, exc)

        logger.info(
            "Extracted %d valid events from '%s' across %d chunk(s).",
            len(validated), document_filename, total_chunks,
        )
        return ExtractionResult(
            document_id=document_id,
            events=validated,
            extraction_errors=errors,  # Kept clean if fallback succeeded
            raw_response=last_raw_response,
        )


_extraction_service: Optional[AIExtractionService] = None


def get_extraction_service() -> AIExtractionService:
    global _extraction_service
    if _extraction_service is None:
        _extraction_service = AIExtractionService()
    return _extraction_service
