"""Features router — GET /api/features"""
from __future__ import annotations

from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.db_models import Feature
from app.schemas.events import FeatureOut
from app.schemas.queries import FeatureStateOut
from app.services.historical_state import HistoricalStateService

router = APIRouter(prefix="/features", tags=["features"])


@router.get("", response_model=list[FeatureOut])
async def list_features(
    project_id: str = Query(...),
    is_implemented: Optional[bool] = Query(None),
    is_removed: Optional[bool] = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
) -> list[FeatureOut]:
    """List all known features for a project."""
    filters = [Feature.project_id == project_id]
    if is_implemented is not None:
        filters.append(Feature.is_implemented == is_implemented)
    if is_removed is not None:
        filters.append(Feature.is_removed == is_removed)

    from sqlalchemy import and_
    result = await db.execute(
        select(Feature).where(and_(*filters))
        .order_by(Feature.canonical_name.asc())
        .limit(limit).offset(offset)
    )
    return [FeatureOut.model_validate(f) for f in result.scalars().all()]


@router.get("/{feature_id}", response_model=FeatureOut)
async def get_feature(
    feature_id: str,
    db: AsyncSession = Depends(get_db),
) -> FeatureOut:
    result = await db.execute(select(Feature).where(Feature.id == feature_id))
    feat = result.scalars().first()
    if not feat:
        raise HTTPException(status_code=404, detail="Feature not found")
    return FeatureOut.model_validate(feat)


@router.get("/{feature_id}/state", response_model=FeatureStateOut)
async def get_feature_state(
    feature_id: str,
    as_of_event_date: Optional[date] = Query(None, description="Event date cutoff (YYYY-MM-DD)"),
    as_of_ingestion_date: Optional[date] = Query(None, description="Knowledge cutoff (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
) -> FeatureStateOut:
    """
    Reconstruct the historical state of a feature as of an event date and optional ingestion cutoff.
    Strictly adheres to Rules A-H (Approved != Implemented, Removal history preserved, Supersession discounts).
    """
    state = await HistoricalStateService.reconstruct_feature_state(
        db=db,
        feature_id=feature_id,
        as_of_event_date=as_of_event_date,
        as_of_ingestion_date=as_of_ingestion_date,
    )
    if not state:
        raise HTTPException(status_code=404, detail="Feature not found")
    return state


