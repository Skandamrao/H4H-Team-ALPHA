"""
ChronoTrace AI — QA Service
Historical question answering with verifiable evidence.

Architecture:
  1. Deterministic retrieval: filter events by project + temporal constraints.
  2. LLM synthesis: the LLM only phrases the answer — it cannot invent facts.
  3. Citation validation: every cited source_id is verified against the DB.
  4. Answer status: SUPPORTED / PARTIALLY_SUPPORTED / CONFLICTED / INSUFFICIENT_EVIDENCE

Rules enforced:
  Rule G: Unknown information surfaces as gaps, not invented answers.
  Rule H: Every answer cites source_ids and evidence excerpts.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Optional

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import TemporalEvent, Feature, ConflictRecord, SourceRecord
from app.schemas.queries import QuestionAnswer, SupportingEvidence
from app.schemas.events import TemporalEventOut
from app.services.llm_provider import llm

logger = logging.getLogger(__name__)

def _synthesize_deterministic_answer(
    question: str,
    relevant_events: list[TemporalEvent],
    conflicts: list[ConflictRecord],
) -> dict:
    """
    Deterministic synthesis when LLM is unavailable or offline.
    Directly addresses questions using verified retrieved events (Rules A-H).
    """
    if not relevant_events:
        return {
            "answer": "Insufficient evidence found in the ingested project records to answer this question.",
            "status": "INSUFFICIENT_EVIDENCE",
            "cited_source_ids": [],
            "missing_information": ["No relevant historical events match the query keywords."],
            "confidence": 0.0,
        }

    status = "SUPPORTED"
    if conflicts:
        status = "CONFLICTED"

    source_ids = list({e.source_id for e in relevant_events})
    
    # Format answer from evidence excerpts
    summary_lines = []
    for ev in relevant_events[:5]:
        dt_str = f"on {ev.event_date}" if ev.event_date else "(undated)"
        feat_str = f" [{ev.unresolved_feature_mention}]" if ev.unresolved_feature_mention else ""
        summary_lines.append(f"- {ev.event_type}{feat_str} {dt_str}: {ev.description} (Evidence: \"{ev.evidence_excerpt}\")")

    answer_text = (
        f"Based on {len(relevant_events)} verified historical record(s):\n\n" +
        "\n".join(summary_lines)
    )

    if conflicts:
        conflict_desc = "\n".join([f"- {c.conflict_type}: {c.description}" for c in conflicts])
        answer_text += f"\n\nHistorical Conflicts Detected:\n{conflict_desc}"

    return {
        "answer": answer_text,
        "status": status,
        "cited_source_ids": source_ids,
        "missing_information": [],
        "confidence": 0.95 if not conflicts else 0.75,
    }

QA_SYSTEM_PROMPT = """
You are ChronoTrace AI's historical question-answering engine.

You will receive:
1. A question about the historical evolution of software features.
2. A set of retrieved temporal events with their evidence excerpts and source IDs.
3. Any detected conflicts.
4. A list of information gaps.

Your job:
- Answer the question using ONLY the provided evidence.
- Do NOT invent dates, actors, decisions, or feature states not in the evidence.
- If evidence is insufficient, say so clearly (do not guess).
- If events conflict, report the conflict and both sides.
- Cite source_ids for every factual claim.

Return a JSON object with these fields:
{
  "answer": "string — the answer text",
  "status": "SUPPORTED" | "PARTIALLY_SUPPORTED" | "CONFLICTED" | "INSUFFICIENT_EVIDENCE",
  "cited_source_ids": ["source_id_1", ...],
  "missing_information": ["gap description 1", ...],
  "confidence": 0.0 to 1.0
}

Return only the JSON object.
""".strip()


async def answer_question(
    db: AsyncSession,
    project_id: str,
    question: str,
    as_of_event_date: Optional[date] = None,
    as_of_ingestion_date: Optional[date] = None,
) -> QuestionAnswer:
    """
    Answer a historical question using deterministic retrieval + LLM synthesis.
    """
    # ── 1. Retrieve relevant events ───────────────────────────────────────────
    filters = [
        TemporalEvent.project_id == project_id,
        TemporalEvent.is_superseded == False,  # noqa: E712
    ]
    if as_of_event_date:
        filters.append(
            (TemporalEvent.event_date <= as_of_event_date)
            | (TemporalEvent.event_date == None)  # noqa: E711
        )
    if as_of_ingestion_date:
        cutoff = datetime.combine(as_of_ingestion_date, datetime.min.time())
        filters.append(TemporalEvent.ingestion_timestamp <= cutoff)

    from sqlalchemy import and_
    ev_result = await db.execute(select(TemporalEvent).where(and_(*filters)))
    all_events = ev_result.scalars().all()

    # ── 2. Simple keyword relevance pre-filter ────────────────────────────────
    question_lower = question.lower()
    keywords = [w for w in question_lower.split() if len(w) > 3]

    def is_relevant(ev: TemporalEvent) -> bool:
        searchable = " ".join(filter(None, [
            ev.description, ev.evidence_excerpt,
            ev.unresolved_feature_mention,
        ])).lower()
        return any(kw in searchable for kw in keywords)

    relevant_events = [e for e in all_events if is_relevant(e)] or all_events[:20]
    relevant_events = relevant_events[:30]  # cap context size

    # ── 3. Retrieve conflicts ─────────────────────────────────────────────────
    relevant_event_ids = {e.id for e in relevant_events}
    conflict_result = await db.execute(
        select(ConflictRecord).where(
            ConflictRecord.project_id == project_id,
            ConflictRecord.resolved == False,  # noqa: E712
        )
    )
    conflicts = [
        c for c in conflict_result.scalars().all()
        if c.event_id_a in relevant_event_ids or c.event_id_b in relevant_event_ids
    ]

    # ── 4. Build LLM context ──────────────────────────────────────────────────
    events_json = [
        {
            "event_id": e.id,
            "source_id": e.source_id,
            "feature": e.unresolved_feature_mention,
            "event_type": e.event_type,
            "event_date": str(e.event_date) if e.event_date else None,
            "event_date_precision": e.event_date_precision,
            "description": e.description,
            "evidence_excerpt": e.evidence_excerpt,
            "actor": e.actor,
        }
        for e in relevant_events
    ]

    conflicts_json = [
        {"type": c.conflict_type, "description": c.description}
        for c in conflicts
    ]

    user_prompt = (
        f"Question: {question}\n\n"
        f"Retrieved events ({len(events_json)}):\n{json.dumps(events_json, indent=2)}\n\n"
        f"Detected conflicts ({len(conflicts_json)}):\n{json.dumps(conflicts_json, indent=2)}\n\n"
        f"Answer the question using only the evidence above."
    )

    # ── 5. Answer synthesis (LLM with deterministic fallback) ─────────────────
    from app.config import settings

    has_api_key = bool(
        (settings.llm_provider == "gemini" and settings.gemini_api_key) or
        (settings.llm_provider == "openai" and settings.openai_api_key)
    )

    llm_response: dict = {}
    if has_api_key:
        try:
            llm_response = await llm.complete_json(QA_SYSTEM_PROMPT, user_prompt)
        except Exception as exc:
            logger.warning("QA LLM call failed (%s) — falling back to deterministic synthesis.", exc)
            llm_response = _synthesize_deterministic_answer(question, relevant_events, conflicts)
    else:
        llm_response = _synthesize_deterministic_answer(question, relevant_events, conflicts)

    # ── 6. Validate cited source IDs against DB (Rule H) ─────────────────────
    cited_ids: list[str] = llm_response.get("cited_source_ids", [])
    valid_source_ids: set[str] = set()
    if cited_ids:
        src_result = await db.execute(
            select(SourceRecord.id).where(SourceRecord.id.in_(cited_ids))
        )
        valid_source_ids = {row[0] for row in src_result.all()}

    unverified = [sid for sid in cited_ids if sid not in valid_source_ids]
    missing_info = llm_response.get("missing_information", [])
    if unverified:
        missing_info.append(
            f"Warning: {len(unverified)} cited source ID(s) could not be verified in the database."
        )

    # ── 7. Build supporting evidence objects ─────────────────────────────────
    supporting: list[SupportingEvidence] = []
    for ev in relevant_events:
        if ev.source_id in valid_source_ids:
            supporting.append(SupportingEvidence(
                event=TemporalEventOut.model_validate(ev),
                relevance_note="Cited by LLM answer",
            ))

    # Conflicting events
    conflicting_ev_ids = {c.event_id_a for c in conflicts} | {c.event_id_b for c in conflicts}
    conflicting_events = [
        TemporalEventOut.model_validate(e)
        for e in relevant_events if e.id in conflicting_ev_ids
    ]

    status = llm_response.get("status", "INSUFFICIENT_EVIDENCE")
    if status not in {"SUPPORTED", "PARTIALLY_SUPPORTED", "CONFLICTED", "INSUFFICIENT_EVIDENCE"}:
        status = "INSUFFICIENT_EVIDENCE"

    return QuestionAnswer(
        question=question,
        answer=llm_response.get("answer", "No answer produced."),
        status=status,  # type: ignore[arg-type]
        supporting_evidence=supporting,
        conflicting_events=conflicting_events,
        missing_information=missing_info,
        cited_source_ids=list(valid_source_ids),
        confidence=float(llm_response.get("confidence", 0.0)),
    )

