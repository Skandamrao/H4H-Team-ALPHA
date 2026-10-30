"""Timeline router — GET /api/timeline/{feature_id}"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.queries import FeatureTimeline, ProjectHistoricalStateOut, ProjectTimelineOut
from app.services.temporal_engine import build_feature_timeline, build_project_timeline
from app.services.historical_state import HistoricalStateService

router = APIRouter(prefix="/timeline", tags=["timeline"])


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


@router.get("/project/{project_id}", response_model=ProjectTimelineOut)
async def get_project_timeline(
    project_id: str,
    as_of_event_date: Optional[date] = Query(None, description="Event date cutoff (YYYY-MM-DD)"),
    as_of_ingestion_date: Optional[date] = Query(None, description="Knowledge cutoff (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
) -> ProjectTimelineOut:
    """
    Return the unified chronological timeline for all events across a project.
    Supports bitemporal filtering by event date and/or ingestion cutoff.
    """
    return await build_project_timeline(
        db=db,
        project_id=project_id,
        as_of_event_date=as_of_event_date,
        as_of_ingestion_date=as_of_ingestion_date,
    )


@router.get("/state", response_model=ProjectHistoricalStateOut)
async def get_project_state(
    project_id: str = Query(...),
    as_of_date: Optional[date] = Query(None, description="Reconstruct all feature states as of this event date"),
    as_of_ingestion_date: Optional[date] = Query(None, description="Knowledge cutoff date (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
) -> ProjectHistoricalStateOut:
    """
    Reconstruct the state of ALL features in a project as of a given event date and optional ingestion cutoff.
    Useful for answering 'What was implemented by [date]?' with verifiable historical rigor.
    """
    return await HistoricalStateService.reconstruct_project_state(
        db=db,
        project_id=project_id,
        as_of_event_date=as_of_date,
        as_of_ingestion_date=as_of_ingestion_date,
    )

