"""
Ingestion Orchestrator Service.

Coordinates the full ingestion pipeline:
  1. Validate file type and size.
  2. Compute SHA-256 hash — reject duplicates.
  3. Extract text from document.
  4. Infer document date.
  5. Persist document record.
  6. Run AI event extraction.
  7. Resolve feature entities.
  8. Persist events and evidence.
  9. Update ingestion batch counters.
 10. Trigger conflict detection.

Historical events are NEVER overwritten or deleted.
"""

import logging
import os
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.models import (
    Document, Event, EventEvidence, Feature, FeatureAlias, IngestionBatch, Module, Person
)
from app.schemas.schemas import ExtractedEvent, ProcessingStatus
from app.services.document_processor import (
    compute_file_hash, validate_file_type, extract_text, infer_document_date
)
from app.services.extraction.ai_extractor import get_extraction_service
from app.services.entity_resolution import resolve_or_create_feature
from app.services.conflict_detector import detect_conflicts
from app.services.graph.knowledge_graph import rebuild_graph

logger = logging.getLogger(__name__)


class IngestionError(Exception):
    """Raised when ingestion fails in a way that should be surfaced to the caller."""


def _ensure_upload_dir() -> None:
    os.makedirs(settings.upload_dir, exist_ok=True)


def _save_file(file_bytes: bytes, original_filename: str) -> str:
    """Save *file_bytes* to the upload directory. Returns the saved filename."""
    _ensure_upload_dir()
    unique_name = f"{uuid.uuid4()}_{original_filename}"
    path = os.path.join(settings.upload_dir, unique_name)
    with open(path, "wb") as f:
        f.write(file_bytes)
    return unique_name


def _get_or_create_person(db: Session, name: str) -> Optional[Person]:
    if not name or not name.strip():
        return None
    person = db.query(Person).filter(Person.name == name.strip()).first()
    if person is None:
        person = Person(name=name.strip())
        db.add(person)
        db.flush()
    return person


def _get_or_create_module(db: Session, module_name: str, project_id: Optional[str]) -> Optional[Module]:
    if not module_name or not module_name.strip():
        return None
    canonical = module_name.strip()
    module = db.query(Module).filter(Module.canonical_name == canonical).first()
    if module is None:
        module = Module(project_id=project_id, name=canonical, canonical_name=canonical)
        db.add(module)
        db.flush()
    return module


def _persist_extracted_event(
    db: Session,
    extracted: ExtractedEvent,
    document: Document,
    project_id: Optional[str],
) -> Event:
    """
    Convert an ExtractedEvent schema into ORM objects and persist them.
    """
    # Resolve or create the feature
    feature: Optional[Feature] = None
    if extracted.feature_name:
        feature, _ = resolve_or_create_feature(
            db, extracted.feature_name, project_id, document.id
        )

    # Resolve responsible person
    person = _get_or_create_person(db, extracted.responsible_person or "")

    # Resolve module
    module = _get_or_create_module(db, extracted.module_name or "", project_id)
    if feature and module and not feature.module_id:
        feature.module_id = module.id

    # Parse event date
    event_date: Optional[datetime] = None
    if extracted.event_date:
        try:
            event_date = datetime.fromisoformat(extracted.event_date)
        except ValueError:
            logger.warning("Could not parse event date '%s' — storing as None.", extracted.event_date)

    # Build the Event record
    event = Event(
        feature_id=feature.id if feature else None,
        source_document_id=document.id,
        responsible_person_id=person.id if person else None,
        title=extracted.title,
        description=extracted.description or "",
        event_type=extracted.event_type.value,
        decision_status=extracted.decision_status.value if extracted.decision_status else None,
        feature_name_in_source=extracted.feature_name,
        module_name=extracted.module_name,
        related_feature_names=str(extracted.related_features) if extracted.related_features else None,
        decision_text=extracted.decision,
        reason=extracted.reason,
        supporting_text=extracted.supporting_text or "",
        event_date=event_date,
        event_date_confidence=extracted.event_date_confidence.value,
        confidence_score=extracted.confidence_score,
    )
    db.add(event)
    db.flush()

    # Attach evidence record
    if extracted.supporting_text:
        evidence = EventEvidence(
            event_id=event.id,
            document_id=document.id,
            excerpt=extracted.supporting_text,
            confidence=extracted.confidence_score,
        )
        db.add(evidence)

    # Update feature status based on event type
    if feature:
        _update_feature_status(feature, event)
        if event_date:
            if not feature.first_seen_date or event_date < feature.first_seen_date:
                feature.first_seen_date = event_date
            if not feature.last_event_date or event_date > feature.last_event_date:
                feature.last_event_date = event_date

    return event


def _update_feature_status(feature: Feature, event: Event) -> None:
    """
    Update the feature's current status based on the new event.

    Status is only changed if the new event is chronologically at or after
    the feature's last recorded event — preventing earlier events processed
    out-of-order from reverting a more-advanced status.
    """
    # Define a precedence order so status only moves forward.
    STATUS_PRECEDENCE = {
        "PROPOSED": 1,
        "ACTIVE": 2,
        "DEPRECATED": 3,
        "REMOVED": 4,
    }
    status_map = {
        "FEATURE_INTRODUCED": "ACTIVE",
        "FEATURE_IMPLEMENTED": "ACTIVE",
        "DECISION_APPROVED": "ACTIVE",
        "FEATURE_DEPRECATED": "DEPRECATED",
        "FEATURE_REMOVED": "REMOVED",
        "DECISION_PROPOSED": "PROPOSED",
    }
    new_status = status_map.get(event.event_type)
    if not new_status:
        return

    current = feature.current_status or "PROPOSED"
    # Only allow status to stay the same or advance (not regress).
    if STATUS_PRECEDENCE.get(new_status, 0) >= STATUS_PRECEDENCE.get(current, 0):
        feature.current_status = new_status


def ingest_document(
    db: Session,
    file_bytes: bytes,
    original_filename: str,
    batch_id: Optional[str] = None,
    project_id: Optional[str] = None,
    trigger_rebuild: bool = True,
) -> Document:
    """
    Full ingestion pipeline for a single document.

    Returns the persisted Document record.
    Raises IngestionError on unrecoverable problems.
    """
    # ── 1. Validate file type ──────────────────────────────────────────────────
    is_valid, file_type = validate_file_type(original_filename)
    if not is_valid:
        raise IngestionError(
            f"Unsupported file type '.{file_type}'. Accepted: pdf, txt, md, json."
        )

    # ── 2. Check file size ────────────────────────────────────────────────────
    if len(file_bytes) > settings.max_file_size_bytes:
        raise IngestionError(
            f"File '{original_filename}' exceeds the {settings.max_file_size_mb} MB size limit."
        )

    # ── 3. Compute hash and check for duplicates ───────────────────────────────
    file_hash = compute_file_hash(file_bytes)
    existing = db.query(Document).filter(Document.file_hash == file_hash).first()
    if existing:
        logger.info("Duplicate detected: '%s' matches existing document '%s'.", original_filename, existing.id)
        # Return a lightweight duplicate record (not saved again)
        dup_doc = Document(
            project_id=project_id,
            ingestion_batch_id=batch_id,
            filename=original_filename,
            original_filename=original_filename,
            file_type=file_type,
            file_size_bytes=len(file_bytes),
            file_hash=file_hash,
            processing_status="COMPLETED",
            is_duplicate=True,
            duplicate_of_id=existing.id,
        )
        db.add(dup_doc)
        db.commit()
        db.refresh(dup_doc)
        return dup_doc

    # ── 4. Save file to disk ──────────────────────────────────────────────────
    saved_filename = _save_file(file_bytes, original_filename)

    # ── 5. Create initial Document record ────────────────────────────────────
    doc = Document(
        project_id=project_id,
        ingestion_batch_id=batch_id,
        filename=saved_filename,
        original_filename=original_filename,
        file_type=file_type,
        file_size_bytes=len(file_bytes),
        file_hash=file_hash,
        processing_status="PROCESSING",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # ── 6. Extract text ───────────────────────────────────────────────────────
    try:
        text, page_count = extract_text(file_bytes, file_type)
        doc.extracted_text = text
        doc.page_count = page_count

        # Infer document date from content
        doc_date, date_confidence = infer_document_date(text, original_filename)
        doc.document_date = doc_date
        doc.document_date_confidence = date_confidence
    except Exception as exc:
        doc.processing_status = "FAILED"
        doc.processing_error = str(exc)
        db.commit()
        raise IngestionError(f"Text extraction failed: {exc}") from exc

    # ── 7. AI Event Extraction ────────────────────────────────────────────────
    extraction_errors = []
    new_event_count = 0
    try:
        extractor = get_extraction_service()
        result = extractor.extract_events(doc.id, text, original_filename)
        extraction_errors = result.extraction_errors

        for extracted_event in result.events:
            _persist_extracted_event(db, extracted_event, doc, project_id)
            new_event_count += 1
    except Exception as exc:
        logger.error("Event extraction failed for '%s': %s", original_filename, exc)
        extraction_errors.append(str(exc))

    doc.processing_status = "COMPLETED"
    if extraction_errors:
        doc.processing_error = "; ".join(extraction_errors[:5])

    db.commit()
    db.refresh(doc)

    # ── 8. Update batch counters ──────────────────────────────────────────────
    if batch_id:
        batch = db.get(IngestionBatch, batch_id)
        if batch:
            batch.processed_files += 1
            batch.new_events_extracted += new_event_count
            db.commit()

    # ── 9. Rebuild knowledge graph ────────────────────────────────────────────
    if trigger_rebuild:
        try:
            rebuild_graph(db)
        except Exception as exc:
            logger.warning("Graph rebuild failed: %s", exc)

    logger.info(
        "Ingested '%s': %d events extracted, %d errors.",
        original_filename, new_event_count, len(extraction_errors),
    )
    return doc

