"""
ChronoTrace AI — Event Relation Processor (P07)
Processes and establishes verified relationships between temporal events and features:
  - Fulfills/Implements (Decision -> Implementation link)
  - Supersedes (Revisions & ADR overrides)
  - Explains Change (Modifications linked to prior specifications)
  - Dependencies (Feature -> Target Feature)
"""
from __future__ import annotations

import logging
import uuid
from typing import List, Optional
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import (
    TemporalEvent, EventRelationship, FeatureRelationship, Feature
)

logger = logging.getLogger(__name__)


def _uuid() -> str:
    return str(uuid.uuid4())


class EventRelationProcessor:
    """
    Infers and persists explicit relational links between events based on domain rules.
    """

    @classmethod
    async def process_feature_relations(
        cls,
        db: AsyncSession,
        project_id: str,
        feature_id: str,
    ) -> int:
        """
        Process events for a given feature to generate explicit EventRelationship records.
        Returns the number of new relationships established.
        """
        res = await db.execute(
            select(TemporalEvent).where(
                TemporalEvent.project_id == project_id,
                TemporalEvent.feature_id == feature_id,
            ).order_by(TemporalEvent.event_date)
        )
        events = res.scalars().all()
        created_count = 0

        # 1. Supersession processing (Rule D)
        for ev in events:
            if ev.supersedes_event_id:
                existing = await db.execute(
                    select(EventRelationship).where(
                        EventRelationship.from_event_id == ev.id,
                        EventRelationship.to_event_id == ev.supersedes_event_id,
                        EventRelationship.relationship_type == "SUPERSEDES",
                    )
                )
                if not existing.scalars().first():
                    rel = EventRelationship(
                        id=_uuid(),
                        project_id=project_id,
                        from_event_id=ev.id,
                        to_event_id=ev.supersedes_event_id,
                        relationship_type="SUPERSEDES",
                        description=f"Event {ev.id} supersedes {ev.supersedes_event_id}",
                    )
                    db.add(rel)
                    created_count += 1

                # Mark superseded row
                prior = await db.get(TemporalEvent, ev.supersedes_event_id)
                if prior and not prior.is_superseded:
                    prior.is_superseded = True

        # 2. Decision to Implementation processing (Rule A)
        approvals = [e for e in events if e.event_type == "APPROVED" and not e.is_superseded]
        implementations = [e for e in events if e.event_type == "IMPLEMENTED"]

        for impl in implementations:
            # Find the most recent preceding approval
            preceding_approvals = [
                a for a in approvals
                if a.event_date and impl.event_date and a.event_date <= impl.event_date
            ]
            if preceding_approvals:
                best_approval = max(preceding_approvals, key=lambda a: a.event_date)  # type: ignore[arg-type]
                existing = await db.execute(
                    select(EventRelationship).where(
                        EventRelationship.from_event_id == impl.id,
                        EventRelationship.to_event_id == best_approval.id,
                        EventRelationship.relationship_type == "IMPLEMENTS",
                    )
                )
                if not existing.scalars().first():
                    rel = EventRelationship(
                        id=_uuid(),
                        project_id=project_id,
                        from_event_id=impl.id,
                        to_event_id=best_approval.id,
                        relationship_type="IMPLEMENTS",
                        description=f"Implementation {impl.id} fulfills approved decision {best_approval.id}",
                    )
                    db.add(rel)
                    created_count += 1

        # 3. Modification to Implementation / Decision processing
        modifications = [e for e in events if e.event_type == "MODIFIED"]
        for mod in modifications:
            # Link to preceding implementation or approval
            prior_actions = [
                e for e in events
                if e.id != mod.id and e.event_type in ("IMPLEMENTED", "APPROVED") and
                (e.event_date is None or (mod.event_date and e.event_date <= mod.event_date))
            ]
            if prior_actions:
                target = prior_actions[-1]
                existing = await db.execute(
                    select(EventRelationship).where(
                        EventRelationship.from_event_id == mod.id,
                        EventRelationship.to_event_id == target.id,
                        EventRelationship.relationship_type == "EXPLAINS_CHANGE",
                    )
                )
                if not existing.scalars().first():
                    rel = EventRelationship(
                        id=_uuid(),
                        project_id=project_id,
                        from_event_id=mod.id,
                        to_event_id=target.id,
                        relationship_type="EXPLAINS_CHANGE",
                        description=f"Modification {mod.id} explains changes to prior {target.event_type} {target.id}",
                    )
                    db.add(rel)
                    created_count += 1

        await db.commit()
        return created_count
