"""
ChronoTrace AI — Temporal Engine (P07)
Deterministic chronological reasoning and timeline reconstruction.

Enforces:
  - Partial ordering representation for same-date events (Rule C)
  - Unknown event dates remain uninvented with uncertainty flag
  - Bitemporal query cutoffs (event_date cutoff vs ingestion_timestamp knowledge cutoff)
  - Information gap identification (Rule G)
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import Feature, TemporalEvent, ConflictRecord
from app.schemas.events import TemporalEventOut, FeatureOut
from app.schemas.queries import FeatureTimeline, TimelineEvent, ProjectTimelineOut
from app.services.historical_state import HistoricalStateService
from app.services.conflict_detector import detect_conflicts_for_feature

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


class TemporalEngine:
    """
    Core engine for chronological event ordering and temporal timeline assembly.
    """

    @staticmethod
    def _sort_events(raw_events: List[TemporalEvent]) -> List[TemporalEvent]:
        """
        Sort events chronologically by known event_date, then ingestion_timestamp.
        Events with unknown dates are sorted last.
        """
        def sort_key(e: TemporalEvent):
            if e.event_date:
                return (0, e.event_date, e.ingestion_timestamp)
            return (1, date.max, e.ingestion_timestamp)

        return sorted(raw_events, key=sort_key)

    @classmethod
    def detect_ordering_uncertainty(cls, events: List[TemporalEvent]) -> Dict[str, bool]:
        """
        Identify events where chronological order is uncertain or ambiguous (Requirement C).
        If two events share the exact same event_date and no sequence information exists,
        their relative ordering cannot be assumed.
        """
        uncertain_flags: Dict[str, bool] = {}
        date_counts: Dict[date, List[str]] = {}

        for ev in events:
            if ev.event_date is None:
                # Undated events are always uncertain in ordering
                uncertain_flags[ev.id] = True
            else:
                date_counts.setdefault(ev.event_date, []).append(ev.id)

        for d, ev_ids in date_counts.items():
            if len(ev_ids) > 1:
                # Multiple events on the exact same date without explicit sequence order
                for eid in ev_ids:
                    uncertain_flags[eid] = True

        return uncertain_flags

    @classmethod
    async def build_feature_timeline(
        cls,
        db: AsyncSession,
        feature_id: str,
        as_of_event_date: Optional[date] = None,
        as_of_ingestion_date: Optional[date] = None,
    ) -> Optional[FeatureTimeline]:
        """
        Build a complete chronological timeline for a single feature.
        """
        feat_res = await db.execute(select(Feature).where(Feature.id == feature_id))
        feature = feat_res.scalars().first()
        if not feature:
            return None

        filters = [
            TemporalEvent.feature_id == feature_id,
            TemporalEvent.is_superseded == False,  # noqa: E712
        ]

        if as_of_event_date:
            filters.append(
                (TemporalEvent.event_date <= as_of_event_date)
                | (TemporalEvent.event_date == None)  # noqa: E711
            )

        if as_of_ingestion_date:
            ingestion_cutoff = datetime.combine(as_of_ingestion_date, datetime.max.time())
            filters.append(TemporalEvent.ingestion_timestamp <= ingestion_cutoff)

        ev_result = await db.execute(select(TemporalEvent).where(and_(*filters)))
        raw_events = ev_result.scalars().all()

        sorted_events = cls._sort_events(raw_events)
        uncertainty_map = cls.detect_ordering_uncertainty(sorted_events)

        timeline_events: list[TimelineEvent] = []
        seen_milestones: set[str] = set()

        for ev in sorted_events:
            ev_out = TemporalEventOut.model_validate(ev)
            milestone = None
            if ev.event_type in _MILESTONE_MAP and ev.event_type not in seen_milestones:
                milestone = _MILESTONE_MAP[ev.event_type]
                seen_milestones.add(ev.event_type)

            is_uncertain = uncertainty_map.get(ev.id, False)

            timeline_events.append(
                TimelineEvent(
                    event=ev_out,
                    milestone_label=milestone,
                    order_uncertain=is_uncertain,
                    sequence_ambiguous=is_uncertain,
                )
            )

        # Conflicts
        conflicts = await detect_conflicts_for_feature(db, feature.project_id, feature.id)
        conflict_descs = [c.description for c in conflicts]

        # Information gaps
        gaps = cls._identify_gaps(sorted_events)

        return FeatureTimeline(
            feature=FeatureOut.model_validate(feature),
            events=timeline_events,
            conflicts=conflict_descs,
            gaps=gaps,
            as_of_event_date=as_of_event_date,
            as_of_ingestion_date=as_of_ingestion_date,
        )

    @classmethod
    async def build_project_timeline(
        cls,
        db: AsyncSession,
        project_id: str,
        as_of_event_date: Optional[date] = None,
        as_of_ingestion_date: Optional[date] = None,
    ) -> ProjectTimelineOut:
        """
        Build a project-wide chronological timeline of all events across features.
        Supports bitemporal filtering by event date and knowledge/ingestion date.
        """
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
            ingestion_cutoff = datetime.combine(as_of_ingestion_date, datetime.max.time())
            filters.append(TemporalEvent.ingestion_timestamp <= ingestion_cutoff)

        ev_result = await db.execute(select(TemporalEvent).where(and_(*filters)))
        raw_events = ev_result.scalars().all()

        sorted_events = cls._sort_events(raw_events)
        uncertainty_map = cls.detect_ordering_uncertainty(sorted_events)

        timeline_events: list[TimelineEvent] = []
        for ev in sorted_events:
            ev_out = TemporalEventOut.model_validate(ev)
            milestone = _MILESTONE_MAP.get(ev.event_type)
            is_uncertain = uncertainty_map.get(ev.id, False)

            timeline_events.append(
                TimelineEvent(
                    event=ev_out,
                    milestone_label=milestone,
                    order_uncertain=is_uncertain,
                    sequence_ambiguous=is_uncertain,
                )
            )

        return ProjectTimelineOut(
            project_id=project_id,
            events=timeline_events,
            total_events=len(timeline_events),
            as_of_event_date=as_of_event_date,
            as_of_ingestion_date=as_of_ingestion_date,
        )

    @staticmethod
    def _identify_gaps(events: list[TemporalEvent]) -> list[str]:
        """
        Identify notable gaps in the event sequence without hallucinating facts (Rule G).
        """
        gaps: list[str] = []
        if not events:
            return ["No events found for this feature."]

        unknown_date_count = sum(1 for e in events if e.event_date is None)
        if unknown_date_count:
            gaps.append(
                f"{unknown_date_count} event(s) have no known event date — their chronological position is uncertain."
            )

        types = {e.event_type for e in events}
        if "IMPLEMENTED" in types and "APPROVED" not in types:
            gaps.append(
                "Feature is recorded as IMPLEMENTED but no APPROVED decision record was found. Approval may exist in uningested records."
            )

        if "PROPOSED" in types and "APPROVED" not in types and "REJECTED" not in types:
            gaps.append(
                "Feature has a PROPOSED record but no corresponding APPROVED or REJECTED decision was found."
            )

        return gaps


# Convenience module-level wrappers for existing callers
async def build_feature_timeline(
    db: AsyncSession,
    feature_id: str,
    as_of_event_date: Optional[date] = None,
    as_of_ingestion_date: Optional[date] = None,
) -> Optional[FeatureTimeline]:
    return await TemporalEngine.build_feature_timeline(
        db, feature_id, as_of_event_date, as_of_ingestion_date
    )


async def build_project_timeline(
    db: AsyncSession,
    project_id: str,
    as_of_event_date: Optional[date] = None,
    as_of_ingestion_date: Optional[date] = None,
) -> ProjectTimelineOut:
    return await TemporalEngine.build_project_timeline(
        db, project_id, as_of_event_date, as_of_ingestion_date
    )


async def reconstruct_state_as_of(
    db: AsyncSession,
    project_id: str,
    as_of_date: date,
    as_of_ingestion_date: Optional[date] = None,
) -> dict:
    """
    Reconstruct summary state for all features in a project as of an event date.
    Delegates to HistoricalStateService.
    """
    state_out = await HistoricalStateService.reconstruct_project_state(
        db, project_id, as_of_date, as_of_ingestion_date
    )
    result = {}
    for st in state_out.features:
        result[st.feature_id] = {
            "feature_id": st.feature_id,
            "canonical_name": st.canonical_name,
            "active_name": st.active_name,
            "as_of_date": str(as_of_date),
            "is_proposed": st.is_proposed,
            "is_approved": st.is_approved,
            "is_rejected": st.is_rejected,
            "is_implemented": st.is_implemented,
            "is_removed": st.is_removed,
            "was_implemented": st.was_implemented,
            "is_reintroduced": st.is_reintroduced,
            "modifications_count": st.modifications_count,
            "active_aliases": st.active_aliases,
            "dependencies": st.dependencies,
            "event_count": len(st.supporting_event_ids),
        }
    return result
