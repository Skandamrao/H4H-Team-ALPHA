"""Document ingestion and management routes."""

import logging
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.database import get_db
from app.models.models import Document, IngestionBatch, Event
from app.schemas.schemas import DocumentResponse, DocumentListResponse, IngestionBatchResponse, DashboardStats
from app.services.ingestion_service import ingest_document, IngestionError

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/upload", response_model=List[DocumentResponse], status_code=status.HTTP_201_CREATED)
async def upload_documents(
    files: List[UploadFile] = File(...),
    project_id: Optional[str] = Form(None),
    batch_label: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """
    Upload one or more documents for ingestion.
    Each file is processed: text extracted, AI events extracted, entities resolved.
    Duplicate files (by SHA-256 hash) are flagged but not rejected.
    """
    # Create ingestion batch
    batch = IngestionBatch(
        project_id=project_id,
        label=batch_label or f"Batch {len(files)} files",
        total_files=len(files),
        status="PROCESSING",
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)

    results = []
    failed = 0
    duplicates = 0

    for upload in files:
        try:
            file_bytes = await upload.read()
            doc = ingest_document(
                db=db,
                file_bytes=file_bytes,
                original_filename=upload.filename,
                batch_id=batch.id,
                project_id=project_id,
            )
            if doc.is_duplicate:
                duplicates += 1
            event_count = db.query(func.count(Event.id)).filter(Event.source_document_id == doc.id).scalar() or 0
            doc_response = DocumentResponse(
                id=doc.id,
                filename=doc.filename,
                original_filename=doc.original_filename,
                file_type=doc.file_type,
                file_size_bytes=doc.file_size_bytes,
                document_date=doc.document_date,
                document_date_confidence=doc.document_date_confidence,
                ingested_at=doc.ingested_at,
                processing_status=doc.processing_status,
                processing_error=doc.processing_error,
                page_count=doc.page_count,
                is_duplicate=doc.is_duplicate,
                event_count=event_count,
            )
            results.append(doc_response)
        except IngestionError as exc:
            logger.error("Ingestion error for '%s': %s", upload.filename, exc)
            failed += 1
            results.append(DocumentResponse(
                id="error",
                filename=upload.filename or "unknown",
                original_filename=upload.filename or "unknown",
                file_type="unknown",
                file_size_bytes=0,
                document_date=None,
                document_date_confidence="UNKNOWN",
                ingested_at=datetime.utcnow(),
                processing_status="FAILED",
                processing_error=str(exc),
                page_count=None,
                is_duplicate=False,
                event_count=0,
            ))
        except Exception as exc:
            logger.exception("Unexpected error for '%s'", upload.filename)
            failed += 1

    # Finalize batch
    batch.status = "COMPLETED" if failed == 0 else "FAILED"
    batch.completed_at = datetime.utcnow()
    batch.failed_files = failed
    batch.duplicate_files = duplicates
    db.commit()

    return results


@router.get("/", response_model=DocumentListResponse)
def list_documents(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """List all ingested documents with their event counts."""
    total = db.query(func.count(Document.id)).scalar() or 0
    docs = db.query(Document).order_by(Document.ingested_at.desc()).offset(skip).limit(limit).all()

    results = []
    for doc in docs:
        event_count = db.query(func.count(Event.id)).filter(Event.source_document_id == doc.id).scalar() or 0
        results.append(DocumentResponse(
            id=doc.id,
            filename=doc.filename,
            original_filename=doc.original_filename,
            file_type=doc.file_type,
            file_size_bytes=doc.file_size_bytes,
            document_date=doc.document_date,
            document_date_confidence=doc.document_date_confidence,
            ingested_at=doc.ingested_at,
            processing_status=doc.processing_status,
            processing_error=doc.processing_error,
            page_count=doc.page_count,
            is_duplicate=doc.is_duplicate,
            event_count=event_count,
        ))

    return DocumentListResponse(total=total, documents=results)


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(document_id: str, db: Session = Depends(get_db)):
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    event_count = db.query(func.count(Event.id)).filter(Event.source_document_id == doc.id).scalar() or 0
    return DocumentResponse(
        id=doc.id,
        filename=doc.filename,
        original_filename=doc.original_filename,
        file_type=doc.file_type,
        file_size_bytes=doc.file_size_bytes,
        document_date=doc.document_date,
        document_date_confidence=doc.document_date_confidence,
        ingested_at=doc.ingested_at,
        processing_status=doc.processing_status,
        processing_error=doc.processing_error,
        page_count=doc.page_count,
        is_duplicate=doc.is_duplicate,
        event_count=event_count,
    )


@router.delete("/{document_id}")
def delete_document(document_id: str, db: Session = Depends(get_db)):
    """
    Delete a document and clean up all associated events, evidence,
    and relationships from the temporal knowledge graph.
    """
    import os
    from app.core.config import settings
    from app.models.models import EventEvidence, EventRelationship, Decision, FeatureAlias
    from app.services.graph.knowledge_graph import rebuild_graph
    from app.services.conflict_detector import detect_conflicts

    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    doc_filename = doc.original_filename
    saved_filename = doc.filename

    # 1. Unlink any duplicate references
    db.query(Document).filter(Document.duplicate_of_id == document_id).update({"duplicate_of_id": None})

    # 2. Unlink any feature aliases from this document
    db.query(FeatureAlias).filter(FeatureAlias.source_document_id == document_id).update({"source_document_id": None})

    # 3. Find all events belonging to this document
    events = db.query(Event).filter(Event.source_document_id == document_id).all()
    event_ids = [e.id for e in events]

    if event_ids:
        # Delete decisions linked to these events
        db.query(Decision).filter(Decision.event_id.in_(event_ids)).delete(synchronize_session=False)

        # Delete event relationships (both outgoing and incoming)
        db.query(EventRelationship).filter(
            (EventRelationship.source_event_id.in_(event_ids)) |
            (EventRelationship.target_event_id.in_(event_ids))
        ).delete(synchronize_session=False)

        # Delete all evidence for these events
        db.query(EventEvidence).filter(EventEvidence.event_id.in_(event_ids)).delete(synchronize_session=False)

        # Delete events
        for e in events:
            db.delete(e)

    # 4. Delete any evidence that referenced this document directly
    db.query(EventEvidence).filter(EventEvidence.document_id == document_id).delete(synchronize_session=False)

    # 5. Delete document record
    db.delete(doc)
    db.commit()

    # 6. Delete file from disk if present
    if saved_filename:
        file_path = os.path.join(settings.upload_dir, saved_filename)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError as err:
                logger.warning("Could not delete file '%s' from disk: %s", file_path, err)

    # 7. Update knowledge graph and detect conflicts
    try:
        rebuild_graph(db)
        detect_conflicts(db)
    except Exception as exc:
        logger.warning("Graph rebuild or conflict detection failed after document deletion: %s", exc)

    return {
        "status": "success",
        "message": f"Document '{doc_filename}' and its associated events deleted successfully.",
        "deleted_events_count": len(event_ids),
    }


@router.get("/dashboard/stats", response_model=DashboardStats)
def get_dashboard_stats(db: Session = Depends(get_db)):
    """Return aggregate statistics for the overview dashboard."""
    from app.models.models import Feature, Decision
    from sqlalchemy import distinct

    total_docs = db.query(func.count(Document.id)).scalar() or 0
    total_events = db.query(func.count(Event.id)).scalar() or 0
    total_features = db.query(func.count(Feature.id)).scalar() or 0
    total_decisions = db.query(func.count(Event.id)).filter(
        Event.event_type.in_(["DECISION_PROPOSED", "DECISION_APPROVED", "DECISION_REJECTED"])
    ).scalar() or 0
    total_conflicts = db.query(func.count(Event.id)).filter(Event.has_conflict == True).scalar() or 0

    batches = db.query(IngestionBatch).order_by(IngestionBatch.started_at.desc()).limit(5).all()
    recent_batches = [IngestionBatchResponse(
        id=b.id, label=b.label, started_at=b.started_at, completed_at=b.completed_at,
        status=b.status, total_files=b.total_files, processed_files=b.processed_files,
        failed_files=b.failed_files, duplicate_files=b.duplicate_files,
        new_events_extracted=b.new_events_extracted,
    ) for b in batches]

    # Event type distribution
    from sqlalchemy import text
    type_rows = db.execute(
        text("SELECT event_type, COUNT(*) as cnt FROM events GROUP BY event_type ORDER BY cnt DESC")
    ).fetchall()
    event_dist = [{"event_type": r[0], "count": r[1]} for r in type_rows]

    # Top 5 features by event count for activity widget
    from app.models.models import Feature
    feature_rows = (
        db.query(Feature.canonical_name, func.count(Event.id).label("event_count"))
        .join(Event, Event.feature_id == Feature.id, isouter=True)
        .group_by(Feature.id)
        .order_by(func.count(Event.id).desc())
        .limit(5)
        .all()
    )
    feature_activity = [{"name": r[0], "event_count": r[1]} for r in feature_rows]

    return DashboardStats(
        total_documents=total_docs,
        total_events=total_events,
        total_features=total_features,
        total_decisions=total_decisions,
        total_conflicts=total_conflicts,
        recent_batches=recent_batches,
        event_type_distribution=event_dist,
        feature_activity=feature_activity,
    )


@router.post("/load-sample-data")
def load_sample_dataset(db: Session = Depends(get_db)):
    """Load or reset the synthetic hackathon demonstration dataset."""
    import sys
    import os
    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)

    try:
        from seed_sample_data import seed
        seed()
        return {"message": "Synthetic sample dataset loaded successfully.", "status": "success"}
    except Exception as exc:
        logger.error("Failed to load sample dataset: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to load sample data: {exc}")


@router.post("/reprocess-all")
def reprocess_all_documents(db: Session = Depends(get_db)):
    """
    Reprocess all documents with Groq AI event extraction.
    Always clears previous events before re-extracting to prevent stale data.
    """
    from app.services.extraction.ai_extractor import get_extraction_service
    from app.services.ingestion_service import _persist_extracted_event
    from app.services.graph.knowledge_graph import rebuild_graph
    from app.services.conflict_detector import detect_conflicts
    from app.models.models import EventEvidence

    docs = db.query(Document).filter(Document.is_duplicate == False).all()
    extractor = get_extraction_service()
    reprocessed_count = 0
    total_events_extracted = 0

    for doc in docs:
        if not doc.extracted_text:
            continue

        result = extractor.extract_events(doc.id, doc.extracted_text, doc.original_filename)

        # Always clear previous events to prevent stale data accumulation,
        # regardless of whether extraction returned 0 events or produced errors.
        existing_events = db.query(Event).filter(Event.source_document_id == doc.id).all()
        for ev in existing_events:
            db.query(EventEvidence).filter(EventEvidence.event_id == ev.id).delete()
            db.delete(ev)
        db.flush()

        if result.extraction_errors:
            doc.processing_error = "; ".join(result.extraction_errors[:5])
            doc.processing_status = "FAILED"
        else:
            doc.processing_error = None
            doc.processing_status = "COMPLETED"

        for ext_event in result.events:
            _persist_extracted_event(db, ext_event, doc, doc.project_id)
            total_events_extracted += 1

        reprocessed_count += 1

    db.commit()
    try:
        rebuild_graph(db)
        detect_conflicts(db)
    except Exception as exc:
        logger.warning("Graph rebuild or conflict detection failed during reprocess: %s", exc)

    return {
        "status": "success",
        "documents_reprocessed": reprocessed_count,
        "events_extracted": total_events_extracted,
    }

