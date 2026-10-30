"""
ChronoTrace AI — Ingestion Service
Orchestrates append-only ingestion of source records.

Rule D: Never overwrites existing source records or temporal events.
Rule C: event_date and ingestion_timestamp are always distinct fields.
R10:    Later batches extend history, never replace it.
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import SourceRecord, TemporalEvent, Feature
from app.schemas.ingestion import SourceRecordIn, IngestBatchRequest, IngestBatchResponse, IngestRecordResult
from app.services.extraction_service import extract_events_from_record
from app.services.identity_resolver import resolve_feature_mention, apply_rename
from app.services.conflict_detector import detect_conflicts_for_feature
from app.utils.date_parser import parse_date_expression

def _uuid() -> str:
    return str(uuid.uuid4())

logger = logging.getLogger(__name__)


async def ingest_batch(
    db: AsyncSession,
    request: IngestBatchRequest,
    batch_id: Optional[str] = None,
) -> IngestBatchResponse:
    """
    Ingest a batch of source records.
    All DB writes in this call are appends only (Rule D).
    """
    if not batch_id:
        batch_id = str(uuid.uuid4())

    results: list[IngestRecordResult] = []
    total_events = 0
    total_features = 0
    total_conflicts = 0
    batch_warnings: list[str] = []

    for record_in in request.records:
        result = await _ingest_single_record(db, record_in, batch_id)
        results.append(result)
        total_events += result.events_extracted
        total_features += result.features_identified
        total_conflicts += result.conflicts_detected
        batch_warnings.extend(result.warnings)

    # Final flush — session commit happens in get_db() dependency
    await db.flush()

    return IngestBatchResponse(
        batch_id=batch_id,
        records_processed=len(request.records),
        total_events_extracted=total_events,
        total_features_identified=total_features,
        total_conflicts_detected=total_conflicts,
        results=results,
        warnings=batch_warnings,
    )


async def _ingest_single_record(
    db: AsyncSession,
    record_in: SourceRecordIn,
    batch_id: str,
) -> IngestRecordResult:
    warnings: list[str] = []

    # Parse source date — Rule C
    if record_in.source_date:
        source_date = record_in.source_date
        source_date_raw = record_in.source_date_raw or str(source_date)
    elif record_in.source_date_raw:
        source_date, _, _ = parse_date_expression(record_in.source_date_raw)
        source_date_raw = record_in.source_date_raw
    else:
        source_date = None
        source_date_raw = None
        warnings.append("No source_date provided — document date is unknown.")

    # Persist source record (append-only)
    source = SourceRecord(
        id=_uuid(),
        project_id=record_in.project_id,
        record_type=record_in.record_type,
        title=record_in.title,
        source_date=source_date,
        source_date_raw=source_date_raw,
        content=record_in.content,
        author=record_in.author,
        batch_id=batch_id,
    )
    db.add(source)
    await db.flush()  # get source.id

    # Extract temporal events using LLM
    extracted = await extract_events_from_record(
        project_id=record_in.project_id,
        source_id=source.id,
        record_type=record_in.record_type,
        title=record_in.title,
        source_date=source_date,
        source_date_raw=source_date_raw,
        content=record_in.content,
    )

    features_seen: set[str] = set()
    events_stored = 0

    for ev_create in extracted:
        # Resolve or create feature identity
        feature_id: Optional[str] = None
        mention = ev_create.unresolved_feature_mention

        if mention:
            feature_id = await resolve_feature_mention(
                db=db,
                project_id=record_in.project_id,
                mention=mention,
                source_id=source.id,
                evidence_excerpt=ev_create.evidence_excerpt,
            )
            if feature_id:
                features_seen.add(feature_id)

        # Persist event (append-only)
        db_event = TemporalEvent(
            id=_uuid(),
            project_id=ev_create.project_id,
            feature_id=feature_id,
            unresolved_feature_mention=mention if not feature_id else None,
            event_type=ev_create.event_type,
            description=ev_create.description,
            previous_name=ev_create.previous_name,
            new_name=ev_create.new_name,
            event_date=ev_create.event_date,
            event_date_raw=ev_create.event_date_raw,
            event_date_precision=ev_create.event_date_precision,
            event_date_basis=ev_create.event_date_basis,
            source_id=source.id,
            evidence_excerpt=ev_create.evidence_excerpt,
            actor=ev_create.actor,
            related_event_ids=ev_create.related_event_ids,
            extraction_confidence=ev_create.extraction_confidence,
            needs_review=ev_create.needs_review,
        )
        db.add(db_event)
        await db.flush()

        # Handle renames — update canonical name and add alias (Rule E)
        if ev_create.event_type == "RENAMED" and feature_id and ev_create.new_name:
            await apply_rename(
                db=db,
                feature_id=feature_id,
                new_name=ev_create.new_name,
                source_id=source.id,
                evidence_excerpt=ev_create.evidence_excerpt,
            )

        # Update feature lifecycle flags (derived from events, never from assumptions)
        if feature_id:
            await _update_feature_flags(db, feature_id, ev_create.event_type)

        events_stored += 1

    # Detect conflicts for all touched features
    conflict_count = 0
    for fid in features_seen:
        conflicts = await detect_conflicts_for_feature(db, record_in.project_id, fid)
        conflict_count += len(conflicts)

    return IngestRecordResult(
        source_id=source.id,
        events_extracted=events_stored,
        features_identified=len(features_seen),
        conflicts_detected=conflict_count,
        warnings=warnings,
    )


async def _update_feature_flags(
    db: AsyncSession, feature_id: str, event_type: str
) -> None:
    """
    Update derived lifecycle flags on Feature.
    Rule A: APPROVED event does NOT set is_implemented.
    Rule B: PROPOSED event does NOT set is_approved.
    """
    from sqlalchemy import select
    result = await db.execute(select(Feature).where(Feature.id == feature_id))
    feat = result.scalars().first()
    if not feat:
        return

    if event_type == "APPROVED":
        feat.is_approved = True
    elif event_type == "IMPLEMENTED":
        feat.is_implemented = True          # Rule A: only IMPLEMENTED sets this
    elif event_type == "REMOVED":
        feat.is_removed = True
    # PROPOSED does NOT change is_approved (Rule B)

