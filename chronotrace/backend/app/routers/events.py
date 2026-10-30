"""Events router — GET /api/events"""
from __future__ import annotations

from typing import Optional
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.db_models import TemporalEvent
from app.schemas.events import TemporalEventOut, ConflictOut
from app.models.db_models import ConflictRecord

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=list[TemporalEventOut])
async def list_events(
    project_id: str = Query(...),
    feature_id: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    needs_review: Optional[bool] = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
) -> list[TemporalEventOut]:
    """List temporal events with optional filters."""
    filters = [
        TemporalEvent.project_id == project_id,
        TemporalEvent.is_superseded == False,  # noqa: E712
    ]
    if feature_id:
        filters.append(TemporalEvent.feature_id == feature_id)
    if event_type:
        filters.append(TemporalEvent.event_type == event_type.upper())
    if from_date:
        filters.append(TemporalEvent.event_date >= from_date)
    if to_date:
        filters.append(TemporalEvent.event_date <= to_date)
    if needs_review is not None:
        filters.append(TemporalEvent.needs_review == needs_review)

    from sqlalchemy import and_
    result = await db.execute(
        select(TemporalEvent)
        .where(and_(*filters))
        .order_by(TemporalEvent.event_date.asc().nulls_last(), TemporalEvent.ingestion_timestamp.asc())
        .limit(limit)
        .offset(offset)
    )
    return [TemporalEventOut.model_validate(e) for e in result.scalars().all()]


@router.get("/conflicts", response_model=list[ConflictOut])
async def list_conflicts(
    project_id: str = Query(...),
    resolved: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
) -> list[ConflictOut]:
    """List detected conflicts."""
    filters = [ConflictRecord.project_id == project_id]
    if resolved is not None:
        filters.append(ConflictRecord.resolved == resolved)

    from sqlalchemy import and_
    result = await db.execute(
        select(ConflictRecord).where(and_(*filters))
        .order_by(ConflictRecord.detected_at.desc())
    )
    return [ConflictOut.model_validate(c) for c in result.scalars().all()]


@router.get("/{event_id}", response_model=TemporalEventOut)
async def get_event(
    event_id: str,
    db: AsyncSession = Depends(get_db),
) -> TemporalEventOut:
    from fastapi import HTTPException
    result = await db.execute(select(TemporalEvent).where(TemporalEvent.id == event_id))
    ev = result.scalars().first()
    if not ev:
        raise HTTPException(status_code=404, detail="Event not found")
    return TemporalEventOut.model_validate(ev)

