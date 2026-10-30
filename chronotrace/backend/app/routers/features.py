"""Features router — GET /api/features"""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.db_models import Feature
from app.schemas.events import FeatureOut

router = APIRouter(prefix="/api/features", tags=["features"])


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

