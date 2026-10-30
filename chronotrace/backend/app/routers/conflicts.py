"""
Conflicts Router — /api/conflicts
Inspection and resolution of detected historical contradictions.
"""
from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.db_models import ConflictRecord
from app.schemas.conflicts import ConflictOut, ConflictResolveRequest

router = APIRouter(prefix="/conflicts", tags=["conflicts"])


@router.get("", response_model=List[ConflictOut])
async def list_conflicts(
    project_id: str = Query(...),
    resolved: Optional[bool] = Query(None, description="Filter by resolution status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> List[ConflictOut]:
    """
    List historical conflicts detected across events for a project.
    """
    filters = [ConflictRecord.project_id == project_id]
    if resolved is not None:
        filters.append(ConflictRecord.resolved == resolved)

    result = await db.execute(
        select(ConflictRecord)
        .where(and_(*filters))
        .order_by(ConflictRecord.detected_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return [ConflictOut.model_validate(c) for c in result.scalars().all()]


@router.get("/{conflict_id}", response_model=ConflictOut)
async def get_conflict(
    conflict_id: str,
    db: AsyncSession = Depends(get_db),
) -> ConflictOut:
    """
    Get detailed conflict information by ID.
    """
    result = await db.execute(select(ConflictRecord).where(ConflictRecord.id == conflict_id))
    conflict = result.scalars().first()
    if not conflict:
        raise HTTPException(status_code=404, detail="Conflict record not found")
    return ConflictOut.model_validate(conflict)


@router.post("/{conflict_id}/resolve", response_model=ConflictOut)
async def resolve_conflict(
    conflict_id: str,
    payload: Optional[ConflictResolveRequest] = None,
    db: AsyncSession = Depends(get_db),
) -> ConflictOut:
    """
    Mark a conflict as resolved with audit notes.
    """
    result = await db.execute(select(ConflictRecord).where(ConflictRecord.id == conflict_id))
    conflict = result.scalars().first()
    if not conflict:
        raise HTTPException(status_code=404, detail="Conflict record not found")

    conflict.resolved = True
    if payload and payload.resolution_notes:
        conflict.description = f"{conflict.description} [Resolved: {payload.resolution_notes}]"

    await db.commit()
    await db.refresh(conflict)
    return ConflictOut.model_validate(conflict)
