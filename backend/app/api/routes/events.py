"""Event query and management routes."""

import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.database import get_db
from app.models.models import Event, EventEvidence
from app.schemas.schemas import EventResponse, EventListResponse, EvidenceResponse

router = APIRouter()
logger = logging.getLogger(__name__)


def _build_event_response(event: Event, db: Session) -> EventResponse:
    doc_filename = event.source_document.original_filename if event.source_document else None
    feature_name = event.feature.canonical_name if event.feature else event.feature_name_in_source

    evidence = []
    for ev in event.evidence:
        doc = ev.document
        evidence.append(EvidenceResponse(
            id=ev.id,
            document_id=ev.document_id,
            document_filename=doc.original_filename if doc else "unknown",
            excerpt=ev.excerpt,
            confidence=ev.confidence,
        ))

    return EventResponse(
        id=event.id,
        title=event.title,
        description=event.description,
        event_type=event.event_type,
        decision_status=event.decision_status,
        feature_name=feature_name,
        feature_name_in_source=event.feature_name_in_source,
        module_name=event.module_name,
        reason=event.reason,
        decision_text=event.decision_text,
        supporting_text=event.supporting_text,
        event_date=event.event_date,
        event_date_confidence=event.event_date_confidence,
        recorded_at=event.recorded_at,
        confidence_score=event.confidence_score,
        has_conflict=event.has_conflict,
        source_document_id=event.source_document_id,
        source_document_filename=doc_filename,
        evidence=evidence,
    )


@router.get("/", response_model=EventListResponse)
def list_events(
    skip: int = 0,
    limit: int = 100,
    event_type: Optional[str] = Query(None),
    feature_id: Optional[str] = Query(None),
    has_conflict: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
):
    """List events with optional filtering."""
    query = db.query(Event)
    if isinstance(event_type, str) and event_type:
        query = query.filter(Event.event_type == event_type)
    if isinstance(feature_id, str) and feature_id:
        query = query.filter(Event.feature_id == feature_id)
    if isinstance(has_conflict, bool):
        query = query.filter(Event.has_conflict == has_conflict)

    total = query.count()
    events = query.order_by(Event.event_date.desc().nullslast()).offset(skip).limit(limit).all()

    return EventListResponse(
        total=total,
        events=[_build_event_response(e, db) for e in events],
    )


@router.get("/{event_id}", response_model=EventResponse)
def get_event(event_id: str, db: Session = Depends(get_db)):
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found.")
    return _build_event_response(event, db)
