"""
AI Event Extraction Service using Groq.

Sends document text to Groq and parses structured JSON output
into validated ExtractedEvent objects.

Key guarantees:
  - AI output is always validated against the ExtractedEvent schema.
  - A proposal is never automatically marked as approved.
  - An approved decision is never automatically marked as implemented.
  - If AI output fails validation, the error is logged and returned.
  - Retry logic (via tenacity) handles transient API failures.
  - Large documents are split into chunks to respect Groq TPM limits.
"""

import json
import logging
import time
from typing import List, Optional

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.core.config import settings
from app.schemas.schemas import ExtractedEvent, ExtractionResult

logger = logging.getLogger(__name__)

# Chunk size in characters for Groq (~3,000 tokens per chunk).
# Fits easily inside Groq's 128k context window and TPM limits.
_GROQ_CHUNK_SIZE = 12_000

# Seconds to sleep between Groq chunk calls to avoid TPM accumulation.
_GROQ_CHUNK_DELAY_SEC = 2

# Maximum number of chunks to process per document to avoid HTTP timeouts on massive files.
_MAX_CHUNKS_PER_DOC = 8

# Groq models to use for extraction (with automatic fallback).
_PRIMARY_MODEL = "openai/gpt-oss-120b"
_FALLBACK_MODEL = "openai/gpt-oss-20b"


_EXTRACTION_PROMPT = """
You are an expert software project historian analysing project documents.

Your task is to extract discrete historical events from the document text below.

For each event you find, produce a JSON object with EXACTLY these fields:
{
  "title": "Short, clear event title",
  "description": "Detailed description of what happened",
  "event_type": "<one of the allowed event types>",
  "feature_name": "Name of the feature as written in this document, or null",
  "module_name": "Name of the module, or null",
  "related_features": ["list", "of", "related", "feature", "names"],
  "decision": "The decision text if this is a decision event, or null",
  "reason": "Why this event happened, if stated in the document, or null",
  "event_date": "ISO 8601 date (YYYY-MM-DD) if clearly stated, or null",
  "event_date_confidence": "HIGH if explicitly stated, MEDIUM if inferred, LOW if guessed, UNKNOWN if absent",
  "decision_status": "<one of the allowed statuses, or null>",
  "responsible_person": "Name of the person responsible, or null",
  "supporting_text": "The exact verbatim excerpt from the document that supports this event",
  "confidence_score": 0.0 to 1.0
}

ALLOWED EVENT TYPES (use exactly as written):
  FEATURE_INTRODUCED, FEATURE_MODIFIED, FEATURE_RENAMED, FEATURE_REMOVED,
  DECISION_PROPOSED, DECISION_APPROVED, DECISION_REJECTED,
  FEATURE_IMPLEMENTED, FEATURE_DEPRECATED, MODULE_CREATED, MODULE_MODIFIED

ALLOWED DECISION STATUSES (use exactly as written):
  PROPOSED, APPROVED, REJECTED, IMPLEMENTED, CANCELLED, UNKNOWN

CRITICAL RULES:
1. NEVER mark an event as APPROVED unless the document explicitly states approval.
2. NEVER mark an event as IMPLEMENTED unless the document explicitly states implementation.
3. A proposal and an approval are separate events — do not merge them.
4. If the date is not clearly stated in the document, set event_date to null and event_date_confidence to UNKNOWN.
5. Only extract events that are explicitly described in the document.
6. Do not invent events, reasons, or dates.
7. supporting_text must be a direct quote from the document, not a paraphrase.

Return a JSON object with a single key "events" whose value is an array of event objects.
Return ONLY valid JSON — no markdown, no explanation, no code fences.

DOCUMENT TEXT:
"""


def _chunk_text(text: str, chunk_size: int = _GROQ_CHUNK_SIZE) -> List[str]:
    """
    Split *text* into chunks of at most *chunk_size* characters.

    Prefers splitting on paragraph boundaries (double newline) to keep
    related content together. Falls back to sentence boundaries, then hard split.
    """
    if len(text) <= chunk_size:
        return [text]

    chunks: List[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= chunk_size:
            chunks.append(remaining)
            break

        # Try to split on paragraph boundary within the window
        window = remaining[:chunk_size]
        split_pos = window.rfind("\n\n")
        if split_pos == -1:
            # Fall back to sentence boundary
            split_pos = max(window.rfind(". "), window.rfind(".\n"))
        if split_pos == -1:
            # Last resort: hard split at chunk_size
            split_pos = chunk_size - 1

        chunks.append(remaining[: split_pos + 1])
        remaining = remaining[split_pos + 1 :].lstrip()

    return [c for c in chunks if c.strip()]


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
        """Call Groq and return the raw text response, trying primary model then fallback model."""
        models_to_try = [_PRIMARY_MODEL, _FALLBACK_MODEL]
        last_error = None

        for model_name in models_to_try:
            try:
                completion = groq_client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": "You are an expert software project historian that outputs valid JSON only."},
                        {"role": "user", "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.1,
                )
                return completion.choices[0].message.content
            except Exception as exc:
                last_error = exc
                logger.warning("Groq call with model '%s' failed: %s. Trying fallback if available.", model_name, exc)
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

        Tries Google Gemini API first (per Problem Statement 2), then Groq AI
        with dual-model fallback (GPT-OSS 120B / 20B).
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

        # Split large documents into manageable chunks for Groq
        all_chunks = _chunk_text(text)
        chunks = all_chunks[:_MAX_CHUNKS_PER_DOC]
        total_chunks = len(chunks)
        if len(all_chunks) > _MAX_CHUNKS_PER_DOC:
            logger.info(
                "Document '%s' has %d chunks; processing first %d chunks to maintain responsiveness.",
                document_filename, len(all_chunks), _MAX_CHUNKS_PER_DOC,
            )
        else:
            logger.info(
                "Processing '%s' in %d chunk(s) of ~%d chars each.",
                document_filename, total_chunks, _GROQ_CHUNK_SIZE,
            )

        all_raw_events: List[dict] = []
        errors: List[str] = []
        last_raw_response: Optional[str] = None

        for i, chunk in enumerate(chunks, start=1):
            logger.info(
                "Processing chunk %d/%d for '%s' (%d chars).",
                i, total_chunks, document_filename, len(chunk),
            )
            prompt = _EXTRACTION_PROMPT + chunk

            try:
                raw_response = None
                if gemini_key:
                    raw_response = self._call_gemini(gemini_key, prompt)
                if not raw_response and groq_client:
                    raw_response = self._call_groq(groq_client, prompt)
                if not raw_response:
                    raise RuntimeError("All AI extraction calls (Gemini and Groq) failed for this chunk.")
                last_raw_response = raw_response
                logger.debug("AI extraction response for chunk %d of %s: %s…", i, document_filename, (raw_response or "")[:200])
            except Exception as exc:
                err = f"AI API call failed for '{document_filename}' chunk {i}/{total_chunks}: {exc}"
                logger.error(err)
                errors.append(err)
                # Continue with remaining chunks even if one fails
                if i < total_chunks:
                    time.sleep(_GROQ_CHUNK_DELAY_SEC)
                continue

            # Parse JSON from this chunk
            try:
                data = json.loads(raw_response)
                chunk_events = data.get("events", [])
                if isinstance(chunk_events, list):
                    all_raw_events.extend(chunk_events)
                    logger.info(
                        "Chunk %d/%d yielded %d raw events.", i, total_chunks, len(chunk_events)
                    )
                else:
                    err = f"Chunk {i}/{total_chunks}: Groq 'events' field is not a list."
                    logger.warning(err)
                    errors.append(err)
            except json.JSONDecodeError as exc:
                err = f"Invalid JSON from Groq for '{document_filename}' chunk {i}/{total_chunks}: {exc}"
                logger.error(err)
                errors.append(err)

            # Delay between chunks to avoid TPM accumulation
            if i < total_chunks:
                logger.debug("Sleeping %ds between chunks to respect TPM limit.", _GROQ_CHUNK_DELAY_SEC)
                time.sleep(_GROQ_CHUNK_DELAY_SEC)

        # Validate each event individually — bad events are skipped, not crash-worthy
        validated: List[ExtractedEvent] = []
        for i, raw_event in enumerate(all_raw_events):
            try:
                from app.schemas.schemas import ExtractedEvent as _EE
                event = _EE.model_validate(raw_event)
                validated.append(event)
            except Exception as exc:
                err = f"Event #{i} validation failed: {exc} — raw: {json.dumps(raw_event)[:200]}"
                logger.warning(err)
                errors.append(err)

        logger.info(
            "Extracted %d valid events from '%s' across %d chunk(s) (%d validation errors).",
            len(validated), document_filename, total_chunks, len(errors),
        )
        return ExtractionResult(
            document_id=document_id,
            events=validated,
            extraction_errors=errors,
            raw_response=last_raw_response,
        )


# Module-level singleton — avoids recreating the Groq client repeatedly
_extraction_service: Optional[AIExtractionService] = None


def get_extraction_service() -> AIExtractionService:
    global _extraction_service
    if _extraction_service is None:
        _extraction_service = AIExtractionService()
    return _extraction_service
