"""
ChronoTrace AI — Temporal Engine
Deterministic historical state reconstruction.

Supports:
  - Chronological event ordering for a feature
  - State-as-of-event-date reconstruction
  - State-as-of-ingestion-date (knowledge cutoff)
  - Identification of gaps and unknown periods
  - Multiple modifications, rejected alternatives, reversals, reintroductions

Never uses a "latest event wins" simplification.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import Feature, TemporalEvent, ConflictRecord
from app.schemas.events import TemporalEventOut, FeatureOut
from app.schemas.queries import FeatureTimeline, TimelineEvent

logger = logging.getLogger(__name__)


# Milestone labels for well-known event types
_MILESTONE_MAP = {
    "PROPOSED": "First Proposed",
    "APPROVED": "Approved",
    "IMPLEMENTED": "Implemented",
    "REMOVED": "Removed",
    "RENAMED": "Renamed",
    "REJECTED": "Rejected",
}


async def build_feature_timeline(
    db: AsyncSession,
    feature_id: str,
    as_of_event_date: Optional[date] = None,
    as_of_ingestion_date: Optional[date] = None,
) -> Optional[FeatureTimeline]:
    """
    Build a complete chronological timeline for a feature.

    Two temporal perspectives:
      - as_of_event_date: events with event_date <= cutoff
      - as_of_ingestion_date: events ingested on or before the knowledge cutoff
    """
    # Load feature
    result = await db.execute(select(Feature).where(Feature.id == feature_id))
    feature = result.scalars().first()
    if not feature:
        return None

    # Build event query
    filters = [
        TemporalEvent.feature_id == feature_id,
        TemporalEvent.is_superseded == False,  # noqa: E712
    ]

    if as_of_event_date:
        filters.append(
            (TemporalEvent.event_date <= as_of_event_date)
            | (TemporalEvent.event_date == None)  # noqa: E711 — include unknowns
        )

    if as_of_ingestion_date:
        ingestion_cutoff = datetime.combine(as_of_ingestion_date, datetime.min.time())
        filters.append(TemporalEvent.ingestion_timestamp <= ingestion_cutoff)

    ev_result = await db.execute(
        select(TemporalEvent).where(and_(*filters))
    )
    raw_events = ev_result.scalars().all()

    # Sort: events with known dates first (chronological), unknown dates last
    def sort_key(e: TemporalEvent):
        if e.event_date:
            return (0, e.event_date, e.ingestion_timestamp)
        return (1, date.max, e.ingestion_timestamp)

    sorted_events = sorted(raw_events, key=sort_key)

    # Convert to Pydantic output
    timeline_events: list[TimelineEvent] = []
    seen_milestones: set[str] = set()

    for ev in sorted_events:
        ev_out = TemporalEventOut.model_validate(ev)
        milestone = None
        if ev.event_type in _MILESTONE_MAP and ev.event_type not in seen_milestones:
            milestone = _MILESTONE_MAP[ev.event_type]
            seen_milestones.add(ev.event_type)
        timeline_events.append(TimelineEvent(event=ev_out, milestone_label=milestone))

    # Detect conflicts
    conflict_result = await db.execute(
        select(ConflictRecord).where(
            ConflictRecord.project_id == feature.project_id,
            ConflictRecord.resolved == False,  # noqa: E712
        )
    )
    all_conflicts = conflict_result.scalars().all()

    feature_event_ids = {ev.id for ev in raw_events}
    conflict_descriptions = [
        c.description
        for c in all_conflicts
        if c.event_id_a in feature_event_ids or c.event_id_b in feature_event_ids
    ]

    # Identify gaps
    gaps = _identify_gaps(sorted_events)

    return FeatureTimeline(
        feature=FeatureOut.model_validate(feature),
        events=timeline_events,
        conflicts=conflict_descriptions,
        gaps=gaps,
        as_of_event_date=as_of_event_date,
    )


def _identify_gaps(events: list[TemporalEvent]) -> list[str]:
    """
    Identify notable information gaps in the event sequence.
    Rule G: gaps are reported, not filled with fabricated data.
    """
    gaps: list[str] = []

    if not events:
        return ["No events found for this feature."]

    # Check for events with unknown dates
    unknown_date_count = sum(1 for e in events if e.event_date is None)
    if unknown_date_count:
        gaps.append(
            f"{unknown_date_count} event(s) have no known event date — "
            "their chronological position is uncertain."
        )

    # Check if any event has a date — if timeline is purely undated
    dated = [e for e in events if e.event_date is not None]
    if not dated:
        gaps.append("No events have a known event date; timeline order is based on ingestion order only.")
        return gaps

    # Check for implemented without approved
    types = {e.event_type for e in events}
    if "IMPLEMENTED" in types and "APPROVED" not in types:
        gaps.append(
            "Feature is recorded as IMPLEMENTED but no APPROVED decision record was found. "
            "Approval may exist in unprocessed records."
        )

    # Check for proposed without resolution
    if "PROPOSED" in types and "APPROVED" not in types and "REJECTED" not in types:
        gaps.append(
            "Feature has a PROPOSED record but no corresponding APPROVED or REJECTED decision was found."
        )

    return gaps


async def reconstruct_state_as_of(
    db: AsyncSession,
    project_id: str,
    as_of_date: date,
) -> dict:
    """
    Return a summary of ALL features' state as of a given event date.
    Used for answering "What was implemented by [date]?" questions.
    """
    result = await db.execute(
        select(TemporalEvent).where(
            TemporalEvent.project_id == project_id,
            TemporalEvent.event_date <= as_of_date,
            TemporalEvent.is_superseded == False,  # noqa: E712
        )
    )
    events = result.scalars().all()

    # Group by feature
    feature_events: dict[str, list[TemporalEvent]] = {}
    for ev in events:
        if ev.feature_id:
            feature_events.setdefault(ev.feature_id, []).append(ev)

    state: dict[str, dict] = {}
    for fid, fevents in feature_events.items():
        feat_result = await db.execute(select(Feature).where(Feature.id == fid))
        feat = feat_result.scalars().first()
        if not feat:
            continue

        ev_types = {e.event_type for e in fevents}
        state[fid] = {
            "feature_id": fid,
            "canonical_name": feat.canonical_name,
            "as_of_date": str(as_of_date),
            "is_proposed": "PROPOSED" in ev_types,
            "is_approved": "APPROVED" in ev_types,
            "is_implemented": "IMPLEMENTED" in ev_types,
            "is_removed": "REMOVED" in ev_types,
            "event_count": len(fevents),
        }

    return state

