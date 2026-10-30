"""Feature timeline routes."""

from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.models import Feature, Event, EventEvidence
from app.schemas.schemas import TimelineResponse, TimelineEventResponse, EvidenceResponse

router = APIRouter()


@router.get("/{feature_id}", response_model=TimelineResponse)
def get_feature_timeline(
    feature_id: str,
    from_date: Optional[datetime] = Query(None),
    to_date: Optional[datetime] = Query(None),
    event_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Return the complete ordered timeline of events for a feature."""
    feature = db.get(Feature, feature_id)
    if not feature:
        raise HTTPException(status_code=404, detail="Feature not found.")

    event_query = db.query(Event).filter(Event.feature_id == feature_id)
    if isinstance(from_date, datetime):
        event_query = event_query.filter(Event.event_date >= from_date)
    if isinstance(to_date, datetime):
        event_query = event_query.filter(Event.event_date <= to_date)
    if isinstance(event_type, str) and event_type:
        event_query = event_query.filter(Event.event_type == event_type)

    events = event_query.order_by(Event.event_date.asc().nullslast()).all()

    timeline_events = []
    for e in events:
        doc_filename = e.source_document.original_filename if e.source_document else None
        evidence = [
            EvidenceResponse(
                id=ev.id,
                document_id=ev.document_id,
                document_filename=ev.document.original_filename if ev.document else "unknown",
                excerpt=ev.excerpt,
                confidence=ev.confidence,
            )
            for ev in e.evidence
        ]
        timeline_events.append(TimelineEventResponse(
            event_id=e.id,
            title=e.title,
            event_type=e.event_type,
            decision_status=e.decision_status,
            event_date=e.event_date,
            event_date_confidence=e.event_date_confidence,
            description=e.description,
            reason=e.reason,
            source_document_filename=doc_filename,
            confidence_score=e.confidence_score,
            has_conflict=e.has_conflict,
            evidence=evidence,
        ))

    aliases = [a.alias for a in feature.aliases if not a.is_canonical]

    return TimelineResponse(
        feature_id=feature.id,
        feature_name=feature.canonical_name,
        aliases=aliases,
        events=timeline_events,
    )
