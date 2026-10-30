"""
Historical AI Assistant Service.

Uses Groq and Google Gemini (with deterministic database fallback) to answer questions
about project history strictly grounded on database records and evidence excerpts.

Principles:
  - Answers are always grounded in actual database records.
  - The AI is provided relevant chronological history as context.
  - Directly handles document overview queries ("give overview of document uploaded", "summarize project").
  - Identifies target documents when queries reference them by name, stem, or recency.
  - Refuses to invent missing information or generate fake citations.
  - Conflicting records are explicitly highlighted.
  - Every answer includes genuine citations linked to source documents.
  - If the AI API fails (e.g. rate limit, 400), falls back seamlessly to
    direct database evidence retrieval so the user always receives an accurate, complete answer.
"""

import hashlib
import json
import logging
import re
from typing import List, Optional, Tuple, Set

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.models import Feature, FeatureAlias, Event, Document, EventEvidence
from app.schemas.schemas import AssistantAnswer, Citation

logger = logging.getLogger(__name__)

_ASSISTANT_SYSTEM_PROMPT = """You are ChronoGraph AI — an expert historical analyst and product intelligence system for software projects.

Your role is to answer questions about a software project's history using ONLY the historical records provided in the CONTEXT section below.

STRICT GROUNDING RULES:
1. Base every answer exclusively on the provided CONTEXT records.
2. If the context does not contain enough evidence to answer the question, state that clearly and accurately. Never invent, extrapolate, or speculate about missing facts.
3. Always mention specific dates (e.g., "On October 5, 2024...") when they appear in the records.
4. When multiple records conflict (e.g., one document says approved and another says rejected), describe BOTH sides of the conflict and cite both sources.
5. Distinguish clearly between event lifecycle states: PROPOSED vs. APPROVED vs. IMPLEMENTED vs. DEPRECATED vs. REJECTED.
6. Only cite documents that actually appear in the CONTEXT.
7. When asked for an overview or summary of a document or project records, synthesize a structured summary covering: (a) Document source & scope, (b) Key features/modules introduced or discussed, (c) Key decisions and their approved/proposed status, (d) Identified milestones and verbatim supporting evidence.
8. Rate your confidence as:
   - "High" (strong, explicit direct evidence with exact dates and quotes)
   - "Medium" (partial evidence, inferred dates, or limited details)
   - "Low" (weak or indirect evidence)
   - "Insufficient" (no matching records found in context)

OUTPUT FORMAT — respond with a valid JSON object matching EXACTLY this structure:
{
  "answer": "Clear, factual, narrative answer grounded in the evidence.",
  "historical_events": [
    {"date": "YYYY-MM-DD or Month DD, YYYY", "description": "Specific action/decision recorded in source"}
  ],
  "confidence": "High | Medium | Low | Insufficient",
  "has_conflicts": true or false,
  "conflict_note": "Description of any conflicting records, or null if none",
  "missing_information": "What specific information is absent from the project records, or null"
}

Return ONLY the JSON object — no surrounding markdown fences, no preamble, no commentary. Start directly with {
"""

STOP_WORDS = {
    "a", "an", "the", "and", "or", "in", "on", "at", "to", "for", "of", "with",
    "by", "from", "up", "about", "into", "over", "after", "is", "was", "are",
    "were", "be", "been", "being", "have", "has", "had", "do", "does", "did",
    "what", "when", "where", "which", "who", "whom", "whose", "why", "how",
    "this", "that", "these", "those", "project", "software", "system", "tell", "me",
    "any", "all", "can", "could", "should", "would", "give", "u", "you",
    "add", "added", "adding", "put", "make", "made", "like", "also", "need"
}

OVERVIEW_PATTERNS = [
    "overview", "summary", "summarize", "recap", "all documents",
    "document uploaded", "documents uploaded", "uploaded document",
    "uploaded documents", "uploaded records", "what happened",
    "project history", "project overview", "tell me about",
    "what records", "what features", "all features", "everything",
    "current status", "status of project", "give an overview",
    "give me an overview", "what was discussed", "meeting summary",
    "meeting overview", "transcript overview", "document summary",
]


def _extract_query_tokens(question: str) -> Set[str]:
    """Tokenize question into meaningful lowercase keywords."""
    raw_tokens = re.findall(r"\b[a-zA-Z0-9_-]{2,}\b", question.lower())
    return {t for t in raw_tokens if t not in STOP_WORDS}


# ---------------------------------------------------------------------------
# Module-level response cache — avoids repeated LLM calls for the same question.
# Call clear_answer_cache() whenever documents are added or deleted.
# ---------------------------------------------------------------------------
_answer_cache: dict[str, AssistantAnswer] = {}


def clear_answer_cache() -> None:
    """Clear the in-memory answer cache. Must be called after any DB mutation."""
    global _answer_cache
    _answer_cache.clear()
    logger.info("Assistant answer cache cleared.")


def _build_context(db: Session, question: str) -> Tuple[str, List[Event], List[Document]]:
    """
    Build a focused, chronologically ordered context string for the query.

    Handles:
      1. Specific feature / alias queries.
      2. Specific document queries (by filename, stem, or keywords).
      3. Document overview queries ("give overview of document uploaded", "summarize project").
      4. General project queries.
    """
    q_lower = question.lower()
    tokens = _extract_query_tokens(question)

    all_docs = db.query(Document).order_by(Document.ingested_at.desc()).all()
    all_features = db.query(Feature).all()
    all_events = db.query(Event).all()

    # Detect if query asks for a document overview or project summary
    is_overview_query = any(pat in q_lower for pat in OVERVIEW_PATTERNS)

    # 1. Match documents referenced in the query
    matched_doc_ids: Set[str] = set()
    matched_docs: List[Document] = []

    for doc in all_docs:
        fname = doc.original_filename.lower()
        stem = re.sub(r"\.[^.]+$", "", fname).lower()
        stem_tokens = re.findall(r"\w+", stem)

        # Direct filename match or stem keyword match
        if fname in q_lower or (len(stem) > 5 and stem in q_lower) or any(t in q_lower for t in stem_tokens if len(t) > 4):
            matched_doc_ids.add(doc.id)
            matched_docs.append(doc)

    # If query mentions "document uploaded" / "the document" / "latest document" without a filename,
    # target the most recently uploaded document!
    if not matched_docs and any(p in q_lower for p in ["document uploaded", "uploaded document", "the document", "latest document", "meeting transcript", "transcript"]):
        if all_docs:
            matched_doc_ids.add(all_docs[0].id)
            matched_docs.append(all_docs[0])

    # 2. Match features mentioned in question
    matched_feature_ids: Set[str] = set()
    for feat in all_features:
        feat_name = feat.canonical_name.lower()
        if feat_name in q_lower or any(t in feat_name for t in tokens if len(t) > 3):
            matched_feature_ids.add(feat.id)
            continue
        for alias_obj in feat.aliases:
            alias_lower = alias_obj.alias.lower()
            if alias_lower in q_lower or any(t in alias_lower for t in tokens if len(t) > 3):
                matched_feature_ids.add(feat.id)
                break

    # 3. Score events
    selected_events_set: dict[str, Tuple[float, Event]] = {}

    for ev in all_events:
        score = 0.0

        # High priority for events from matched documents
        if ev.source_document_id and ev.source_document_id in matched_doc_ids:
            score += 25.0

        # High priority for events of matched features
        if ev.feature_id and ev.feature_id in matched_feature_ids:
            score += 20.0

        ev_text = f"{ev.title} {ev.description or ''} {ev.reason or ''} {ev.feature_name_in_source or ''} {ev.module_name or ''} {ev.supporting_text or ''}".lower()

        matched_tokens = sum(1 for t in tokens if t in ev_text)
        # Avoid spurious single-word false matches when neither feature nor document matched
        if not (ev.feature_id and ev.feature_id in matched_feature_ids) and not (ev.source_document_id and ev.source_document_id in matched_doc_ids):
            if len(tokens) >= 2 and matched_tokens < 2:
                matched_tokens = 0

        if matched_tokens > 0:
            score += matched_tokens * 3.0

        if score > 0.0:
            if any(w in q_lower for w in ["why", "reason", "purpose", "motive"]) and ev.reason:
                score += 4.0
            if any(w in q_lower for w in ["approved", "decided", "decision"]) and ev.decision_status == "APPROVED":
                score += 4.0
            if any(w in q_lower for w in ["implemented", "built", "done"]) and ev.event_type == "FEATURE_IMPLEMENTED":
                score += 4.0
            if any(w in q_lower for w in ["conflict", "contradiction", "dispute"]) and ev.has_conflict:
                score += 8.0

            selected_events_set[ev.id] = (score, ev)

    # 4. If overview query, select representative events from matched documents or project
    if is_overview_query:
        if matched_docs:
            # Select events from the matched documents
            target_doc_ids = {d.id for d in matched_docs}
            doc_events = [e for e in all_events if e.source_document_id in target_doc_ids]
            for ev in doc_events:
                selected_events_set[ev.id] = (15.0, ev)
        else:
            # Select representative milestones across all features
            for ev in all_events:
                s = 5.0
                if ev.decision_status in ("APPROVED", "IMPLEMENTED"):
                    s += 5.0
                if ev.event_type in ("FEATURE_INTRODUCED", "DECISION_APPROVED", "FEATURE_RENAMED"):
                    s += 4.0
                selected_events_set[ev.id] = (s, ev)

    ranked = sorted(selected_events_set.values(), key=lambda x: x[0], reverse=True)[:30]
    events_to_include = [item[1] for item in ranked]
    events_to_include.sort(key=lambda e: (e.event_date or e.recorded_at))

    docs_seen: dict[str, Document] = {}
    for d in matched_docs:
        docs_seen[d.id] = d
    for e in events_to_include:
        if e.source_document:
            docs_seen[e.source_document.id] = e.source_document

    context_parts: List[str] = []

    # Prepend document profile if document(s) matched or overview requested
    if matched_docs:
        for md in matched_docs[:2]:
            doc_event_count = sum(1 for e in all_events if e.source_document_id == md.id)
            date_info = md.document_date.strftime('%Y-%m-%d') if md.document_date else 'Extracted from content'
            excerpt = (md.extracted_text or '')[:800].replace('\r\n', ' ').replace('\n', ' ')
            context_parts.append(
                f"[DOCUMENT PROFILE: {md.original_filename}]\n"
                f"  Filename: {md.original_filename}\n"
                f"  File Type: {md.file_type.upper()} | Size: {md.file_size_bytes} bytes\n"
                f"  Document Date: {date_info}\n"
                f"  Status: {md.processing_status} ({doc_event_count} historical events extracted)\n"
                f"  Opening Excerpt: \"{excerpt}\""
            )
    elif is_overview_query and all_docs:
        doc_names = ", ".join([f"{d.original_filename} ({d.file_type.upper()})" for d in all_docs[:8]])
        context_parts.append(
            f"[PROJECT ARCHIVE PROFILE]\n"
            f"  Total Ingested Documents: {len(all_docs)}\n"
            f"  Total Historical Events: {len(all_events)}\n"
            f"  Total Canonical Features: {len(all_features)}\n"
            f"  Documents: {doc_names}"
        )

    for i, event in enumerate(events_to_include, start=1):
        doc = event.source_document
        date_str = event.event_date.strftime("%Y-%m-%d") if event.event_date else "Recorded in document"
        feature_name = event.feature.canonical_name if event.feature else event.feature_name_in_source or "General System"
        doc_name = doc.original_filename if doc else "Unknown Source"

        parts = [
            f"[RECORD #{i}] {event.event_type} (Date: {date_str}, Confidence: {event.event_date_confidence})",
            f"  Feature: {feature_name}",
            f"  Title: {event.title}",
        ]
        if event.decision_status:
            parts.append(f"  Decision Status: {event.decision_status}")
        if event.reason:
            parts.append(f"  Reason / Motivation: {event.reason}")
        if event.description:
            parts.append(f"  Details: {event.description}")
        if event.supporting_text:
            parts.append(f"  Verbatim Evidence: \"{event.supporting_text[:350]}\"")
        parts.append(f"  Source Document: {doc_name}")
        if event.has_conflict and event.conflict_note:
            parts.append(f"  ⚠ HISTORICAL CONFLICT: {event.conflict_note}")

        context_parts.append("\n".join(parts))

    context_text = "\n\n".join(context_parts) if context_parts else "No historical records matched this query."
    return context_text, events_to_include, list(docs_seen.values())


def _extract_citations(events: List[Event], fallback_docs: Optional[List[Document]] = None) -> List[Citation]:
    """Build unique citations from source documents of relevant events."""
    seen: dict[str, Citation] = {}
    for event in events:
        if event.source_document and event.source_document_id not in seen:
            doc = event.source_document
            seen[doc.id] = Citation(
                document_filename=doc.original_filename,
                document_id=doc.id,
                excerpt=event.supporting_text or event.description or "",
            )
    if fallback_docs:
        for doc in fallback_docs:
            if doc.id not in seen:
                seen[doc.id] = Citation(
                    document_filename=doc.original_filename,
                    document_id=doc.id,
                    excerpt=(doc.extracted_text or "")[:200],
                )
    return list(seen.values())


class HistoricalAssistantService:
    """Answers project-history questions using Groq grounded on database context, with database fallback."""

    def __init__(self) -> None:
        pass

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

    def answer(self, db: Session, question: str) -> AssistantAnswer:
        """Generate a grounded answer to *question* using the database records."""
        cache_key = hashlib.md5(question.lower().strip().encode()).hexdigest()
        if cache_key in _answer_cache:
            logger.info("Returning cached assistant answer for question hash %s.", cache_key)
            return _answer_cache[cache_key]

        creds = self._get_credentials()
        gemini_key = creds.get("gemini")
        groq_key = creds.get("groq")

        if not gemini_key and not groq_key:
            return self._answer_from_database(db, question)

        context_text, events, documents = _build_context(db, question)

        if len(context_text) > 5_000:
            logger.info("Context text is %d chars — trimming to 5000 chars.", len(context_text))
            context_text = context_text[:5_000] + "\n\n[Context trimmed to fit token limits]"

        full_prompt = f"CONTEXT:\n{context_text}\n\nQUESTION:\n{question}"

        raw = None
        last_exc = None

        # 1. Try Google Gemini API (gemini-2.5-flash) with fast 5.0s timeout
        if gemini_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=gemini_key)
                model = genai.GenerativeModel(
                    "gemini-2.5-flash",
                    system_instruction=_ASSISTANT_SYSTEM_PROMPT,
                    generation_config={"response_mime_type": "application/json", "temperature": 0.1},
                )
                resp = model.generate_content(full_prompt, request_options={"timeout": 5.0})
                raw = resp.text
            except Exception as exc:
                last_exc = exc
                logger.warning("Gemini assistant call failed (timeout or quota): %s. Falling back to Groq.", exc)

        # 2. Try Groq AI (GPT-OSS 120B / 20B / Llama 3.3) with 8.0s timeout
        if not raw and groq_key:
            models_to_try = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "llama-3.3-70b-versatile", "llama-3.1-8b-instant"]
            for model_name in models_to_try:
                # Attempt with strict JSON mode
                try:
                    import groq
                    client = groq.Groq(api_key=groq_key, timeout=8.0)
                    completion = client.chat.completions.create(
                        model=model_name,
                        messages=[
                            {"role": "system", "content": _ASSISTANT_SYSTEM_PROMPT},
                            {"role": "user", "content": full_prompt},
                        ],
                        response_format={"type": "json_object"},
                        temperature=0.1,
                        timeout=8.0,
                    )
                    raw = completion.choices[0].message.content
                    if raw and raw.strip():
                        break
                except Exception as exc:
                    last_exc = exc
                    logger.warning("Groq JSON mode call with model '%s' failed: %s. Retrying without response_format...", model_name, exc)

                # Fallback attempt: plain text mode without response_format constraint
                try:
                    import groq
                    client = groq.Groq(api_key=groq_key, timeout=8.0)
                    completion = client.chat.completions.create(
                        model=model_name,
                        messages=[
                            {"role": "system", "content": _ASSISTANT_SYSTEM_PROMPT},
                            {"role": "user", "content": f"{full_prompt}\n\nIMPORTANT: Output ONLY a JSON object starting directly with {{"},
                        ],
                        temperature=0.1,
                        timeout=8.0,
                    )
                    raw = completion.choices[0].message.content
                    if raw and raw.strip():
                        break
                except Exception as exc:
                    last_exc = exc
                    logger.warning("Groq plain text assistant call with '%s' failed: %s", model_name, exc)

        if not raw:
            logger.warning("All AI assistant models failed. Falling back to direct database reasoning: %s", last_exc)
            return self._answer_from_database(db, question)

        # Parse JSON from model output
        try:
            cleaned_raw = raw.strip()
            if cleaned_raw.startswith("```json"):
                cleaned_raw = cleaned_raw[7:]
            if cleaned_raw.startswith("```"):
                cleaned_raw = cleaned_raw[3:]
            if cleaned_raw.endswith("```"):
                cleaned_raw = cleaned_raw[:-3]
            cleaned_raw = cleaned_raw.strip()

            start = cleaned_raw.find("{")
            end = cleaned_raw.rfind("}")
            if start != -1 and end != -1 and end > start:
                cleaned_raw = cleaned_raw[start : end + 1]

            data = json.loads(cleaned_raw)
        except Exception as exc:
            logger.error("Assistant JSON parse failed: %s\nRaw: %s", exc, (raw or "")[:400])
            return self._answer_from_database(db, question)

        citations = _extract_citations(events, documents)

        result = AssistantAnswer(
            question=question,
            answer=data.get("answer", "No answer generated."),
            historical_events=data.get("historical_events", []),
            supporting_evidence=citations[:6],
            confidence=data.get("confidence", "Medium"),
            has_conflicts=data.get("has_conflicts", False),
            conflict_note=data.get("conflict_note"),
            missing_information=data.get("missing_information"),
        )
        _answer_cache[cache_key] = result
        return result

    def _answer_from_database(self, db: Session, question: str) -> AssistantAnswer:
        """Grounded factual answer retrieved directly from database records without external AI call."""
        context_text, relevant, docs = _build_context(db, question)

        if not relevant and not docs:
            return AssistantAnswer(
                question=question,
                answer=(
                    "Based on available historical records in ChronoGraph AI, there is insufficient evidence to answer this question. "
                    "The system strictly refuses to speculate or invent missing project history."
                ),
                historical_events=[],
                supporting_evidence=[],
                confidence="Insufficient",
                missing_information="No records matching the query keywords were found in the current documents.",
            )

        events_data = []
        conflicts_found = []
        summary_points = []

        is_overview_query = any(pat in question.lower() for pat in OVERVIEW_PATTERNS)

        for ev in relevant:
            d_str = ev.event_date.strftime("%B %d, %Y") if ev.event_date else "Document record"
            feat_name = ev.feature.canonical_name if ev.feature else ev.feature_name_in_source or "Feature"
            events_data.append({"date": d_str, "description": f"{ev.title}: {ev.description or ''}"})

            reason_part = f" (Reason: {ev.reason})" if ev.reason else ""
            status_part = f" [Status: {ev.decision_status}]" if ev.decision_status else ""
            summary_points.append(f"• On {d_str}, {ev.title}{reason_part}{status_part}.")

            if ev.has_conflict and ev.conflict_note:
                conflicts_found.append(ev.conflict_note)

        # Overview narrative builder
        if is_overview_query and docs:
            doc_names = ", ".join([d.original_filename for d in docs])
            answer_text = (
                f"### ChronoGraph AI — Document & Historical Overview\n\n"
                f"**Source Document(s) Analyzed:** {doc_names}\n"
                f"**Extracted Records:** {len(relevant)} historical events, proposals, and architectural decisions identified.\n\n"
                f"**Key Historical Milestones & Decisions:**\n"
                + "\n".join(summary_points[:10])
            )
        else:
            answer_text = (
                f"Based on the project's historical records, here is what occurred regarding your inquiry:\n\n"
                + "\n".join(summary_points[:8])
            )

        citations = _extract_citations(relevant, docs)

        result = AssistantAnswer(
            question=question,
            answer=answer_text,
            historical_events=events_data[:10],
            supporting_evidence=citations[:6],
            confidence="High" if len(relevant) >= 2 else "Medium",
            has_conflicts=bool(conflicts_found),
            conflict_note="; ".join(conflicts_found) if conflicts_found else None,
        )
        cache_key = hashlib.md5(question.lower().strip().encode()).hexdigest()
        _answer_cache[cache_key] = result
        return result


_assistant: Optional[HistoricalAssistantService] = None


def get_assistant() -> HistoricalAssistantService:
    global _assistant
    if _assistant is None:
        _assistant = HistoricalAssistantService()
    return _assistant
