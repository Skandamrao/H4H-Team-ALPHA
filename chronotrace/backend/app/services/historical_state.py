"""
ChronoTrace AI — Historical State Reconstruction Service (P07)
Calculates exact point-in-time feature states using deterministic event-sourcing principles.

Invariants enforced:
  - APPROVED != IMPLEMENTED (Rule A)
  - PROPOSED != APPROVED (Rule B)
  - REMOVED does not erase prior implementation history (was_implemented remains True)
  - Reintroduction accounts for earlier removal without destroying history
  - Superseded decisions are discounted up to cutoff date
  - Bitemporal support: event_date cutoff + ingestion_timestamp knowledge cutoff
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import Feature, TemporalEvent, ConflictRecord
from app.schemas.queries import FeatureStateOut, ProjectHistoricalStateOut
from app.services.conflict_detector import detect_conflicts_for_feature

logger = logging.getLogger(__name__)


class HistoricalStateService:
    """
    Reconstructs historical project and feature states as-of any point in time.
    """

    @staticmethod
    def _get_event_sort_key(ev: TemporalEvent):
        """
        Deterministic sorting key for events:
        (has_date, event_date, ingestion_timestamp)
        """
        if ev.event_date:
            return (0, ev.event_date, ev.ingestion_timestamp)
        return (1, date.max, ev.ingestion_timestamp)

    @classmethod
    async def reconstruct_feature_state(
        cls,
        db: AsyncSession,
        feature_id: str,
        as_of_event_date: Optional[date] = None,
        as_of_ingestion_date: Optional[date] = None,
    ) -> Optional[FeatureStateOut]:
        """
        Reconstruct a single feature's exact state as of a given event date and/or ingestion date.
        """
        feat_res = await db.execute(select(Feature).where(Feature.id == feature_id))
        feature = feat_res.scalars().first()
        if not feature:
            return None

        # Build bitemporal filter
        filters = [TemporalEvent.feature_id == feature_id]

        if as_of_event_date:
            # Include events up to event cutoff, or undated events
            filters.append(
                (TemporalEvent.event_date <= as_of_event_date) | (TemporalEvent.event_date == None)  # noqa: E711
            )

        if as_of_ingestion_date:
            ingestion_cutoff = datetime.combine(as_of_ingestion_date, datetime.max.time())
            filters.append(TemporalEvent.ingestion_timestamp <= ingestion_cutoff)

        ev_res = await db.execute(select(TemporalEvent).where(and_(*filters)))
        eligible_events = ev_res.scalars().all()

        # Handle supersession as of the cutoff:
        # An event is superseded ONLY if its superseding event occurred on or before the cutoff!
        active_events: List[TemporalEvent] = []
        superseded_event_ids = set()

        for ev in eligible_events:
            if ev.supersedes_event_id:
                # This event supersedes an earlier event
                superseded_event_ids.add(ev.supersedes_event_id)

        for ev in eligible_events:
            if ev.id not in superseded_event_ids:
                active_events.append(ev)

        # Sort chronologically
        sorted_events = sorted(active_events, key=cls._get_event_sort_key)

        # Event-sourcing state calculation
        canonical_name = feature.canonical_name
        active_name = canonical_name
        is_proposed = False
        is_approved = False
        is_rejected = False
        was_implemented = False
        is_currently_implemented = False
        is_removed = False
        is_reintroduced = False
        modifications_count = 0
        active_aliases: list[str] = []
        dependencies: list[str] = []
        supporting_event_ids: list[str] = []
        gaps: list[str] = []

        last_removal_date: Optional[date] = None

        for ev in sorted_events:
            supporting_event_ids.append(ev.id)
            ev_type = ev.event_type

            # Check unknown dates
            if ev.event_date is None:
                gaps.append(f"Event '{ev.description[:60]}...' has unknown date; state timing is partial.")

            if ev_type == "PROPOSED":
                is_proposed = True
                if is_removed and last_removal_date and ev.event_date and ev.event_date > last_removal_date:
                    is_reintroduced = True
                    is_removed = False

            elif ev_type == "APPROVED":
                is_approved = True
                is_rejected = False  # Approval establishes positive decision

            elif ev_type == "REJECTED":
                is_rejected = True
                is_approved = False  # Rejection overturns unfulfilled approval

            elif ev_type == "IMPLEMENTED":
                was_implemented = True
                is_currently_implemented = True
                is_removed = False
                if is_removed and last_removal_date and ev.event_date and ev.event_date > last_removal_date:
                    is_reintroduced = True

            elif ev_type == "MODIFIED":
                modifications_count += 1

            elif ev_type == "RENAMED":
                if ev.new_name:
                    active_name = ev.new_name
                    if ev.previous_name and ev.previous_name not in active_aliases:
                        active_aliases.append(ev.previous_name)
                    if ev.new_name not in active_aliases:
                        active_aliases.append(ev.new_name)

            elif ev_type == "REMOVED":
                is_removed = True
                is_currently_implemented = False  # Removed features are not currently implemented
                if ev.event_date:
                    last_removal_date = ev.event_date

            elif ev_type == "DEPENDENCY_ADDED":
                dep_desc = ev.description.replace("Dependency on", "").strip()
                if dep_desc and dep_desc not in dependencies:
                    dependencies.append(dep_desc)

        # Invariant checks:
        if is_currently_implemented and not is_approved:
            gaps.append("Feature is implemented without an explicit recorded approval record.")

        # Conflicts
        conflicts = await detect_conflicts_for_feature(db, feature.project_id, feature.id)
        conflict_descs = [c.description for c in conflicts]

        return FeatureStateOut(
            feature_id=feature.id,
            canonical_name=canonical_name,
            active_name=active_name,
            as_of_event_date=as_of_event_date,
            as_of_ingestion_date=as_of_ingestion_date,
            is_proposed=is_proposed,
            is_approved=is_approved,
            is_rejected=is_rejected,
            is_implemented=is_currently_implemented,
            is_removed=is_removed,
            was_implemented=was_implemented,
            is_reintroduced=is_reintroduced,
            modifications_count=modifications_count,
            active_aliases=active_aliases,
            dependencies=dependencies,
            supporting_event_ids=supporting_event_ids,
            conflicts=conflict_descs,
            gaps=gaps,
        )

    @classmethod
    async def reconstruct_project_state(
        cls,
        db: AsyncSession,
        project_id: str,
        as_of_event_date: Optional[date] = None,
        as_of_ingestion_date: Optional[date] = None,
    ) -> ProjectHistoricalStateOut:
        """
        Reconstruct states for all features in a project as of a given cutoff.
        """
        feat_res = await db.execute(
            select(Feature).where(Feature.project_id == project_id)
        )
        features = feat_res.scalars().all()

        feature_states: List[FeatureStateOut] = []
        for feat in features:
            st = await cls.reconstruct_feature_state(
                db=db,
                feature_id=feat.id,
                as_of_event_date=as_of_event_date,
                as_of_ingestion_date=as_of_ingestion_date,
            )
            if st and (st.is_proposed or st.is_approved or st.was_implemented or st.is_removed or st.is_rejected):
                feature_states.append(st)

        return ProjectHistoricalStateOut(
            project_id=project_id,
            as_of_event_date=as_of_event_date,
            as_of_ingestion_date=as_of_ingestion_date,
            total_features=len(feature_states),
            features=feature_states,
        )
