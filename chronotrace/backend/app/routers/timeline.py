"""Timeline router — GET /api/timeline/{feature_id}"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.queries import FeatureTimeline
from app.services.temporal_engine import build_feature_timeline, reconstruct_state_as_of

router = APIRouter(prefix="/api/timeline", tags=["timeline"])


@router.get("/feature/{feature_id}", response_model=FeatureTimeline)
async def get_feature_timeline(
    feature_id: str,
    as_of_event_date: Optional[date] = Query(None, description="Event date cutoff (YYYY-MM-DD)"),
    as_of_ingestion_date: Optional[date] = Query(None, description="Knowledge cutoff (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
) -> FeatureTimeline:
    """
    Return the full chronological timeline for a single feature.
    Supports temporal filtering by event date and/or ingestion date.
    """
    timeline = await build_feature_timeline(
        db=db,
        feature_id=feature_id,
        as_of_event_date=as_of_event_date,
        as_of_ingestion_date=as_of_ingestion_date,
    )
    if not timeline:
        raise HTTPException(status_code=404, detail="Feature not found")
    return timeline


@router.get("/state", response_model=dict)
async def get_project_state(
    project_id: str = Query(...),
    as_of_date: date = Query(..., description="Reconstruct all feature states as of this event date"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Reconstruct the state of ALL features in a project as of a given date.
    Useful for answering 'What was implemented by [date]?'
    """
    state = await reconstruct_state_as_of(db, project_id, as_of_date)
    return {"as_of_date": str(as_of_date), "features": list(state.values())}

