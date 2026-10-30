"""
ChronoTrace AI — Ingestion Service
Orchestrates append-only ingestion of source records.

Requirements enforced:
  - Rule C: event_date, source_date, and ingestion_timestamp are always distinct fields.
  - Rule D: Never overwrites existing source records or temporal events.
  - Rule H: Every event has traceable evidence linked to its source document.
  - R10:    Later batches extend history, never replace it.
  - Idempotency: Repeated upload does not duplicate records or extraction effects.
  - Fault tolerance: Per-record errors do not abort the entire batch.
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import (
    Project, IngestionBatch, SourceRecord, TemporalEvent, Feature, EventEvidence
)
from app.schemas.ingestion import (
    SourceRecordIn, IngestBatchRequest, IngestBatchResponse, IngestRecordResult
)
from app.services.extraction_service import extract_events_from_record
from app.services.identity_resolver import resolve_feature_mention, apply_rename
from app.services.conflict_detector import detect_conflicts_for_feature
from app.services.event_relation_processor import EventRelationProcessor
from app.services.document_parser import compute_fingerprint
from app.utils.date_parser import parse_date_expression

def _uuid() -> str:
    return str(uuid.uuid4())

def _now() -> datetime:
    return datetime.now(timezone.utc)

logger = logging.getLogger(__name__)


async def _ensure_project(db: AsyncSession, project_id: str) -> Project:
    """Ensure project exists in the database for foreign key integrity."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalars().first()
    if not project:
        project = Project(
            id=project_id,
            name=project_id,
            description=f"Workspace for project {project_id}",
            created_at=_now(),
        )
        db.add(project)
        await db.flush()
    return project


async def ingest_batch(
    db: AsyncSession,
    request: IngestBatchRequest,
    batch_id: Optional[str] = None,
) -> IngestBatchResponse:
    """
    Ingest a batch of source records with full idempotency and fault tolerance.
    """
    if not batch_id:
        batch_id = request.batch_id or str(uuid.uuid4())

    target_project_ids = {r.project_id for r in request.records}
    for pid in target_project_ids:
        await _ensure_project(db, pid)

    primary_pid = request.records[0].project_id

    # Create IngestionBatch entry
    batch_record = IngestionBatch(
        id=batch_id,
        project_id=primary_pid,
        records_count=len(request.records),
        events_extracted=0,
        failed_count=0,
        duplicate_count=0,
        status="processing",
        created_at=_now(),
        notes=request.notes or f"Mode: {request.mode}",
    )
    db.add(batch_record)
    await db.flush()

    results: list[IngestRecordResult] = []
    total_events = 0
    total_features = 0
    total_conflicts = 0
    successful_count = 0
    failed_count = 0
    duplicate_count = 0
    batch_warnings: list[str] = []

    for idx, record_in in enumerate(request.records):
        try:
            # Per-record processing with idempotency and isolation
            result = await _ingest_single_record(db, record_in, batch_id)
            results.append(result)

            if result.status == "duplicate":
                duplicate_count += 1
                batch_warnings.append(f"Record #{idx+1} ('{record_in.title or 'Untitled'}') is a duplicate; skipped extraction.")
            elif result.status == "success":
                successful_count += 1
                total_events += result.events_extracted
                total_features += result.features_identified
                total_conflicts += result.conflicts_detected
                batch_warnings.extend(result.warnings)
            else:
                failed_count += 1
        except Exception as exc:
            logger.error("Failed processing record #%d: %s", idx, exc, exc_info=True)
            failed_count += 1
            results.append(
                IngestRecordResult(
                    source_id="",
                    status="failed",
                    events_extracted=0,
                    features_identified=0,
                    conflicts_detected=0,
                    warnings=[f"Failed processing record: {str(exc)}"],
                    error=str(exc),
                )
            )

    # Update batch record metrics
    batch_record.events_extracted = total_events
    batch_record.failed_count = failed_count
    batch_record.duplicate_count = duplicate_count
    batch_record.status = "completed" if failed_count == 0 else "partial_failure"
    batch_record.completed_at = _now()

    await db.flush()

    return IngestBatchResponse(
        batch_id=batch_id,
        mode=request.mode,
        records_processed=len(request.records),
        successful_records=successful_count,
        failed_records=failed_count,
        duplicate_records=duplicate_count,
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

    if not record_in.content or not record_in.content.strip():
        raise ValueError("Record content cannot be empty.")

    # Ensure project exists
    await _ensure_project(db, record_in.project_id)

    # Parse source date — Rule C (never defaulted to today)
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

    # Compute deterministic content fingerprint for idempotency
    fingerprint = compute_fingerprint(
        project_id=record_in.project_id,
        record_type=record_in.record_type,
        title=record_in.title,
        author=record_in.author,
        source_date_raw=source_date_raw,
        content=record_in.content,
    )

    # Check for duplicate within the same project (Idempotency requirement)
    dup_query = await db.execute(
        select(SourceRecord).where(
            SourceRecord.project_id == record_in.project_id,
            SourceRecord.content_fingerprint == fingerprint,
        )
    )
    existing_source = dup_query.scalars().first()

    if existing_source:
        # Existing document detected: return its ID, do not duplicate events
        return IngestRecordResult(
            source_id=existing_source.id,
            status="duplicate",
            events_extracted=0,
            features_identified=0,
            conflicts_detected=0,
            warnings=["Duplicate source detected. Extraction skipped."],
        )

    # Persist brand new source record (append-only)
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
        content_fingerprint=fingerprint,
        file_reference=record_in.file_reference,
        metadata_json=record_in.metadata or {},
    )
    db.add(source)
    await db.flush()

    # Extract temporal events
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
        event_id = _uuid()
        db_event = TemporalEvent(
            id=event_id,
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
            evidence_offset_start=ev_create.evidence_offset_start,
            evidence_offset_end=ev_create.evidence_offset_end,
            actor=ev_create.actor,
            related_event_ids=ev_create.related_event_ids,
            extraction_confidence=ev_create.extraction_confidence,
            needs_review=ev_create.needs_review,
        )
        db.add(db_event)
        await db.flush()

        # Persist granular EventEvidence record (Rule H)
        db_evidence = EventEvidence(
            id=_uuid(),
            event_id=event_id,
            source_id=source.id,
            exact_quote=ev_create.evidence_excerpt,
            context_note=f"Extracted from {source.record_type} ({source.title or 'Untitled'})",
            created_at=_now(),
        )
        db.add(db_evidence)

        # Handle renames — update canonical name and add alias (Rule E)
        if ev_create.event_type == "RENAMED" and feature_id and ev_create.new_name:
            await apply_rename(
                db=db,
                feature_id=feature_id,
                new_name=ev_create.new_name,
                source_id=source.id,
                evidence_excerpt=ev_create.evidence_excerpt,
            )

        # Update feature lifecycle flags
        if feature_id:
            await _update_feature_flags(db, feature_id, ev_create.event_type)

        events_stored += 1

    # Detect conflicts and process relationships for all touched features
    conflict_count = 0
    for fid in features_seen:
        conflicts = await detect_conflicts_for_feature(db, record_in.project_id, fid)
        conflict_count += len(conflicts)
        await EventRelationProcessor.process_feature_relations(db, record_in.project_id, fid)

    return IngestRecordResult(
        source_id=source.id,
        status="success",
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
    result = await db.execute(select(Feature).where(Feature.id == feature_id))
    feat = result.scalars().first()
    if not feat:
        return

    if event_type == "APPROVED":
        feat.is_approved = True
    elif event_type == "IMPLEMENTED":
        feat.is_implemented = True
    elif event_type == "REMOVED":
        feat.is_removed = True
