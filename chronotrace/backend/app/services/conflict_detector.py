"""
ChronoTrace AI — Conflict Detector

Detects GENUINE contradictions between temporal events.
Rule F: Proposal → Approval → Implementation is NORMAL PROGRESSION, not conflict.
Only flags events that make incompatible claims in the same time period.
"""
from __future__ import annotations

import logging
import uuid
from datetime import date
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.models.db_models import TemporalEvent as TemporalEventModel

def _uuid() -> str:
    return str(uuid.uuid4())

logger = logging.getLogger(__name__)

# Normal lifecycle progressions — these are NEVER conflicts (Rule F)
_NORMAL_PROGRESSIONS = {
    ("PROPOSED", "APPROVED"),
    ("PROPOSED", "REJECTED"),
    ("APPROVED", "IMPLEMENTED"),
    ("PROPOSED", "IMPLEMENTED"),
    ("IMPLEMENTED", "MODIFIED"),
    ("IMPLEMENTED", "REMOVED"),
    ("MODIFIED", "REMOVED"),
    ("REMOVED", "PROPOSED"),   # reintroduction
    ("REMOVED", "IMPLEMENTED"),
}


def _is_normal_progression(type_a: str, type_b: str) -> bool:
    """Return True if type_a → type_b (or vice-versa) is a normal lifecycle step."""
    pair = (type_a, type_b)
    reverse = (type_b, type_a)
    return pair in _NORMAL_PROGRESSIONS or reverse in _NORMAL_PROGRESSIONS


def _dates_overlap(
    date_a: Optional[date], date_b: Optional[date], window_days: int = 30
) -> bool:
    """True if both dates are non-null and within window_days of each other."""
    if date_a is None or date_b is None:
        return False
    return abs((date_a - date_b).days) <= window_days


async def detect_conflicts_for_feature(
    db: "AsyncSession",
    project_id: str,
    feature_id: str,
) -> list:
    """
    Check all non-superseded events for a feature and detect genuine conflicts.
    Returns newly created ConflictRecord objects (not yet committed).
    """
    from sqlalchemy import select
    from app.models.db_models import ConflictRecord, TemporalEvent

    result = await db.execute(
        select(TemporalEvent).where(
            TemporalEvent.project_id == project_id,
            TemporalEvent.feature_id == feature_id,
            TemporalEvent.is_superseded == False,  # noqa: E712
        )
    )
    events = result.scalars().all()

    new_conflicts = []

    for i in range(len(events)):
        for j in range(i + 1, len(events)):
            a, b = events[i], events[j]
            conflict = _check_pair(a, b)
            if conflict:
                existing = await db.execute(
                    select(ConflictRecord).where(
                        ConflictRecord.event_id_a == a.id,
                        ConflictRecord.event_id_b == b.id,
                    )
                )
                if existing.scalars().first() is None:
                    rec = ConflictRecord(
                        id=_uuid(),
                        project_id=project_id,
                        event_id_a=a.id,
                        event_id_b=b.id,
                        conflict_type=conflict["type"],
                        description=conflict["description"],
                    )
                    db.add(rec)
                    new_conflicts.append(rec)
                    logger.warning(
                        "Conflict detected for feature %s: %s",
                        feature_id, conflict["description"],
                    )

    return new_conflicts


def _check_pair(
    a: TemporalEvent, b: TemporalEvent
) -> Optional[dict]:
    """
    Check a pair of events for genuine conflict. Returns conflict dict or None.
    Rule F: Normal progressions are excluded.
    """
    ta, tb = a.event_type, b.event_type

    # Same-type conflicts (e.g. two APPROVED events on the same feature)
    if ta == tb == "APPROVED" and _dates_overlap(a.event_date, b.event_date, 0):
        return {
            "type": "DUPLICATE_APPROVAL",
            "description": (
                f"Two APPROVED events for the same feature on the same date: "
                f"event {a.id} (source {a.source_id}) and event {b.id} (source {b.source_id})."
            ),
        }

    # Approved then Rejected in overlapping window (contradictory status)
    if {ta, tb} == {"APPROVED", "REJECTED"} and _dates_overlap(a.event_date, b.event_date, 7):
        return {
            "type": "APPROVED_AND_REJECTED",
            "description": (
                f"Feature recorded as both APPROVED and REJECTED within 7 days: "
                f"events {a.id} and {b.id}."
            ),
        }

    # IMPLEMENTED before PROPOSED (temporal impossibility when both dates are exact)
    if ta == "IMPLEMENTED" and tb == "PROPOSED":
        if (
            a.event_date_precision == "exact"
            and b.event_date_precision == "exact"
            and a.event_date is not None
            and b.event_date is not None
            and a.event_date < b.event_date
        ):
            return {
                "type": "IMPLEMENTED_BEFORE_PROPOSED",
                "description": (
                    f"Feature shows IMPLEMENTED ({a.event_date}) before PROPOSED ({b.event_date}): "
                    f"events {a.id} and {b.id}."
                ),
            }

    if ta == "PROPOSED" and tb == "IMPLEMENTED":
        if (
            a.event_date_precision == "exact"
            and b.event_date_precision == "exact"
            and a.event_date is not None
            and b.event_date is not None
            and b.event_date < a.event_date
        ):
            return {
                "type": "IMPLEMENTED_BEFORE_PROPOSED",
                "description": (
                    f"Feature shows IMPLEMENTED ({b.event_date}) before PROPOSED ({a.event_date}): "
                    f"events {a.id} and {b.id}."
                ),
            }

    return None
