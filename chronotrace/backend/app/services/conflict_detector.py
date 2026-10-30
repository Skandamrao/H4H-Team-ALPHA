"""
ChronoTrace AI — Conflict Detector (P07)

Detects GENUINE contradictions between temporal events.
Rule F: Proposal → Approval → Implementation → Modification is NORMAL PROGRESSION, not conflict.
Distinguishes supersession (valid historical revisions) from unresolvable contradictions.
Preserves both source claims in ConflictRecord without deleting history.
"""
from __future__ import annotations

import logging
import uuid
from datetime import date
from typing import Optional, TYPE_CHECKING, List, Dict, Any

from sqlalchemy import select
from app.models.db_models import ConflictRecord, TemporalEvent

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

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
    ("REMOVED", "PROPOSED"),      # Reintroduction
    ("REMOVED", "IMPLEMENTED"),   # Reintroduction and ship
}


def _is_normal_progression(type_a: str, type_b: str) -> bool:
    """Return True if type_a → type_b is a legitimate historical progression."""
    return (type_a, type_b) in _NORMAL_PROGRESSIONS


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
) -> List[ConflictRecord]:
    """
    Check all non-superseded events for a feature and detect genuine conflicts.
    Returns list of ConflictRecord objects (persisting new ones if found).
    """
    result = await db.execute(
        select(TemporalEvent).where(
            TemporalEvent.project_id == project_id,
            TemporalEvent.feature_id == feature_id,
            TemporalEvent.is_superseded == False,  # noqa: E712
        ).order_by(TemporalEvent.event_date)
    )
    events = result.scalars().all()

    existing_conflicts_res = await db.execute(
        select(ConflictRecord).where(
            ConflictRecord.project_id == project_id,
            ConflictRecord.resolved == False,  # noqa: E712
        )
    )
    existing_conflicts = existing_conflicts_res.scalars().all()
    existing_pairs = {(c.event_id_a, c.event_id_b) for c in existing_conflicts} | {
        (c.event_id_b, c.event_id_a) for c in existing_conflicts
    }

    all_feature_conflicts = [
        c for c in existing_conflicts
        if c.event_id_a in {e.id for e in events} or c.event_id_b in {e.id for e in events}
    ]

    for i in range(len(events)):
        for j in range(i + 1, len(events)):
            a, b = events[i], events[j]
            if (a.id, b.id) in existing_pairs:
                continue

            conflict = _check_pair(a, b)
            if conflict:
                rec = ConflictRecord(
                    id=_uuid(),
                    project_id=project_id,
                    event_id_a=a.id,
                    event_id_b=b.id,
                    conflict_type=conflict["type"],
                    description=conflict["description"],
                )
                db.add(rec)
                all_feature_conflicts.append(rec)
                existing_pairs.add((a.id, b.id))
                logger.warning("Conflict detected for feature %s: %s", feature_id, conflict["description"])

    return all_feature_conflicts


def _check_pair(
    a: TemporalEvent, b: TemporalEvent
) -> Optional[dict]:
    """
    Check a pair of events for genuine conflict. Returns conflict dict or None.
    Rule F: Normal progressions and explicit supersessions are excluded.
    """
    ta, tb = a.event_type, b.event_type

    # 1. Supersession exclusion: if either event explicitly supersedes the other, no conflict
    if a.supersedes_event_id == b.id or b.supersedes_event_id == a.id:
        return None

    # Check for text indicating supersession
    if (b.description and "supersedes" in b.description.lower()) or (a.description and "supersedes" in a.description.lower()):
        return None

    # 2. Check if normal chronological progression (Rule F)
    # If a occurred before b and a -> b is a normal progression, it is not a conflict!
    if a.event_date and b.event_date and a.event_date < b.event_date:
        if _is_normal_progression(ta, tb):
            return None
    elif b.event_date and a.event_date and b.event_date < a.event_date:
        if _is_normal_progression(tb, ta):
            return None

    # 3. Duplicate conflicting approval on the exact same date
    if ta == tb == "APPROVED" and a.source_id != b.source_id and _dates_overlap(a.event_date, b.event_date, 0):
        return {
            "type": "DUPLICATE_APPROVAL",
            "description": (
                f"Two conflicting APPROVED events for the same feature on the same date: "
                f"event {a.id} (source {a.source_id}) and event {b.id} (source {b.source_id})."
            ),
        }

    # 4. Approved and Rejected in overlapping window without supersession
    if {ta, tb} == {"APPROVED", "REJECTED"} and _dates_overlap(a.event_date, b.event_date, 7):
        return {
            "type": "APPROVED_AND_REJECTED",
            "description": (
                f"Contradictory status claims: Feature recorded as both APPROVED and REJECTED "
                f"within 7 days without explicit supersession link: events {a.id} and {b.id}."
            ),
        }

    # 5. IMPLEMENTED before PROPOSED (temporal impossibility when both dates are exact)
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
                    f"Feature recorded as IMPLEMENTED ({a.event_date}) before PROPOSED ({b.event_date}): "
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
                    f"Feature recorded as IMPLEMENTED ({b.event_date}) before PROPOSED ({a.event_date}): "
                    f"events {a.id} and {b.id}."
                ),
            }

    # 6. Same-day Contradictory REMOVED and IMPLEMENTED
    if {ta, tb} == {"REMOVED", "IMPLEMENTED"} and _dates_overlap(a.event_date, b.event_date, 0):
        return {
            "type": "REMOVED_AND_IMPLEMENTED_SAME_DAY",
            "description": (
                f"Incompatible status: Feature recorded as both REMOVED and IMPLEMENTED on the same day: "
                f"events {a.id} and {b.id}."
            ),
        }

    return None
