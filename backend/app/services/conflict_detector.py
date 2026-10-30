"""
Conflict Detection Service.

Detects contradictory historical records within the same feature:
  - Contradictory decision statuses (approved vs rejected on same date)
  - Conflicting event dates for the same event type
  - Inconsistent feature status across records

Conflicts are flagged on events — records are NEVER deleted.
Manual review is required to resolve conflicts.
"""

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import List, Tuple

from sqlalchemy.orm import Session

from app.models.models import Event, Feature
from app.schemas.schemas import ConflictRecord, EventResponse, EvidenceResponse

logger = logging.getLogger(__name__)

# Two events within this many days are considered "same day" for conflict purposes
DATE_PROXIMITY_DAYS = 2


def _event_to_response(event: Event) -> EventResponse:
    """Convert an ORM Event to the API response schema."""
    doc_filename = event.source_document.original_filename if event.source_document else None
    feature_name = event.feature.canonical_name if event.feature else event.feature_name_in_source

    evidence = [
        EvidenceResponse(
            id=ev.id,
            document_id=ev.document_id,
            document_filename=ev.document.original_filename if ev.document else "unknown",
            excerpt=ev.excerpt,
            confidence=ev.confidence,
        )
        for ev in event.evidence
    ]

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


def _dates_are_close(date_a: datetime, date_b: datetime) -> bool:
    return abs((date_a - date_b).days) <= DATE_PROXIMITY_DAYS


def detect_conflicts(db: Session) -> List[ConflictRecord]:
    """
    Scan all features and their events for contradictions.
    Returns a list of ConflictRecord objects describing each conflict.
    """
    conflicts: List[ConflictRecord] = []

    features = db.query(Feature).all()
    for feature in features:
        events = sorted(
            [e for e in feature.events if e.event_date is not None],
            key=lambda e: e.event_date,
        )

        # Group events by type for comparison
        decision_events = [e for e in events if e.event_type in (
            "DECISION_PROPOSED", "DECISION_APPROVED", "DECISION_REJECTED"
        )]

        # ── Conflict 1: Approved AND Rejected on approximately the same date ──
        approved = [e for e in decision_events if e.decision_status == "APPROVED"]
        rejected = [e for e in decision_events if e.decision_status == "REJECTED"]

        for ea in approved:
            for er in rejected:
                if ea.event_date and er.event_date and _dates_are_close(ea.event_date, er.event_date):
                    conflict = ConflictRecord(
                        feature_id=feature.id,
                        feature_name=feature.canonical_name,
                        conflict_type="DECISION_CONFLICT",
                        event_a=_event_to_response(ea),
                        event_b=_event_to_response(er),
                        description=(
                            f"'{feature.canonical_name}' has conflicting decision records: "
                            f"approved on {ea.event_date.date()} AND rejected on {er.event_date.date()}."
                        ),
                    )
                    conflicts.append(conflict)

                    # Mark both events as conflicted in the database
                    if not ea.has_conflict:
                        ea.has_conflict = True
                        ea.conflict_note = f"Contradicted by rejection record {er.id}"
                    if not er.has_conflict:
                        er.has_conflict = True
                        er.conflict_note = f"Contradicted by approval record {ea.id}"

        # ── Conflict 2: Feature implemented before it was approved ──
        impl_events = [e for e in events if e.event_type == "FEATURE_IMPLEMENTED"]
        approved_dates = [e.event_date for e in approved if e.event_date]

        for ie in impl_events:
            if ie.event_date and approved_dates:
                earliest_approval = min(approved_dates)
                if ie.event_date < earliest_approval:
                    # Find the approval event for the conflict record
                    earliest_approval_event = next(
                        (e for e in approved if e.event_date == earliest_approval), None
                    )
                    if earliest_approval_event:
                        conflict = ConflictRecord(
                            feature_id=feature.id,
                            feature_name=feature.canonical_name,
                            conflict_type="STATUS_CONFLICT",
                            event_a=_event_to_response(ie),
                            event_b=_event_to_response(earliest_approval_event),
                            description=(
                                f"'{feature.canonical_name}' was marked as implemented on "
                                f"{ie.event_date.date()} but was not approved until "
                                f"{earliest_approval.date()}."
                            ),
                        )
                        conflicts.append(conflict)

        # ── Conflict 3: Multiple INTRODUCED events with conflicting dates ──
        introduced = [e for e in events if e.event_type == "FEATURE_INTRODUCED" and e.event_date is not None]
        if len(introduced) > 1:
            for i in range(len(introduced)):
                for j in range(i + 1, len(introduced)):
                    ea, eb = introduced[i], introduced[j]
                    if not _dates_are_close(ea.event_date, eb.event_date):
                        conflict = ConflictRecord(
                            feature_id=feature.id,
                            feature_name=feature.canonical_name,
                            conflict_type="DATE_CONFLICT",
                            event_a=_event_to_response(ea),
                            event_b=_event_to_response(eb),
                            description=(
                                f"'{feature.canonical_name}' has conflicting introduction dates: "
                                f"{ea.event_date.date()} in source vs {eb.event_date.date()}."
                            ),
                        )
                        conflicts.append(conflict)
                        if not ea.has_conflict:
                            ea.has_conflict = True
                            ea.conflict_note = f"Conflicting introduction date with event {eb.id}"
                        if not eb.has_conflict:
                            eb.has_conflict = True
                            eb.conflict_note = f"Conflicting introduction date with event {ea.id}"

    try:
        db.commit()
    except Exception as exc:
        logger.warning("Could not commit conflict flags: %s", exc)
        db.rollback()

    logger.info("Conflict detection complete: %d conflicts found.", len(conflicts))
    return conflicts

