"""
Repository functions for TemporalEvent, SourceRecord, and EventEvidence entities.
Enforces append-only historical invariants (Rule D & Rule H).
"""
from __future__ import annotations

import uuid
from typing import Optional, List
from datetime import date, datetime, timezone
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.db_models import TemporalEvent, SourceRecord, EventEvidence, EventRelationship

def _uuid() -> str:
    return str(uuid.uuid4())

def _now() -> datetime:
    return datetime.now(timezone.utc)

class EventRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, event_id: str) -> Optional[TemporalEvent]:
        result = await self.db.execute(select(TemporalEvent).where(TemporalEvent.id == event_id))
        return result.scalars().first()

    async def insert_event(
        self,
        project_id: str,
        source_id: str,
        event_type: str,
        description: str,
        evidence_excerpt: str,
        feature_id: Optional[str] = None,
        unresolved_feature_mention: Optional[str] = None,
        event_date: Optional[date] = None,
        event_date_raw: Optional[str] = None,
        event_date_precision: str = "unknown",
        event_date_basis: str = "unknown",
        actor: Optional[str] = None,
        supersedes_event_id: Optional[str] = None,
    ) -> TemporalEvent:
        """
        Append a new temporal event. Never mutates existing history (Rule D).
        """
        event_id = _uuid()
        event = TemporalEvent(
            id=event_id,
            project_id=project_id,
            feature_id=feature_id,
            unresolved_feature_mention=unresolved_feature_mention,
            event_type=event_type,
            description=description,
            event_date=event_date,
            event_date_raw=event_date_raw,
            event_date_precision=event_date_precision,
            event_date_basis=event_date_basis,
            source_id=source_id,
            evidence_excerpt=evidence_excerpt,
            actor=actor,
            supersedes_event_id=supersedes_event_id,
            is_superseded=False,
            ingestion_timestamp=_now(),
        )
        self.db.add(event)
        await self.db.flush()

        # Add explicit evidence row
        evidence = EventEvidence(
            id=_uuid(),
            event_id=event_id,
            source_id=source_id,
            exact_quote=evidence_excerpt,
            created_at=_now(),
        )
        self.db.add(evidence)
        await self.db.flush()

        return event

    async def link_events(
        self,
        project_id: str,
        from_event_id: str,
        to_event_id: str,
        relationship_type: str,
        description: Optional[str] = None,
    ) -> EventRelationship:
        """Create explicit causal or revision edge between events."""
        rel = EventRelationship(
            id=_uuid(),
            project_id=project_id,
            from_event_id=from_event_id,
            to_event_id=to_event_id,
            relationship_type=relationship_type,
            description=description,
            created_at=_now(),
        )
        self.db.add(rel)
        await self.db.flush()
        return rel

    async def list_by_feature(
        self,
        project_id: str,
        feature_id: str,
        as_of_date: Optional[date] = None,
    ) -> List[TemporalEvent]:
        filters = [
            TemporalEvent.project_id == project_id,
            TemporalEvent.feature_id == feature_id,
            TemporalEvent.is_superseded == False,
        ]
        if as_of_date:
            filters.append(
                (TemporalEvent.event_date <= as_of_date) | (TemporalEvent.event_date == None)
            )

        result = await self.db.execute(
            select(TemporalEvent)
            .where(and_(*filters))
            .order_by(TemporalEvent.event_date.asc().nulls_last())
        )
        return list(result.scalars().all())

