"""
ChronoTrace AI — Temporal Knowledge Graph Router
Exposes endpoints for the graph view and graph relation queries.
"""
from __future__ import annotations

from datetime import date
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.queries import TemporalGraphOut
from app.schemas.events import TemporalEventOut
from app.services.graph_service import GraphService

router = APIRouter(prefix="/graph", tags=["graph"])


@router.get("", response_model=TemporalGraphOut)
async def get_project_knowledge_graph(
    project_id: str = Query("proj-alpha", description="Project identifier"),
    as_of_event_date: Optional[date] = Query(None, description="Event date cutoff (YYYY-MM-DD)"),
    as_of_ingestion_date: Optional[date] = Query(None, description="Knowledge cutoff (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
) -> TemporalGraphOut:
    """
    Get the temporal knowledge graph for a project with features, events, decisions, and relationships.
    """
    return await GraphService.get_project_graph(
        db=db,
        project_id=project_id,
        as_of_event_date=as_of_event_date,
        as_of_ingestion_date=as_of_ingestion_date,
    )


@router.get("/features/{feature_id}/events", response_model=List[TemporalEventOut])
async def get_feature_events_graph(
    feature_id: str,
    as_of_event_date: Optional[date] = Query(None, description="Event date cutoff (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
) -> List[TemporalEventOut]:
    """Get all events associated with a specific feature in the knowledge graph."""
    events = await GraphService.get_feature_events(db, feature_id, as_of_event_date)
    return [TemporalEventOut.model_validate(e) for e in events]


@router.get("/features/{feature_id}/decision-links", response_model=Dict[str, Any])
async def get_feature_decision_to_implementation(
    feature_id: str,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Get the explicit decision-to-implementation link for a feature."""
    return await GraphService.get_decision_to_implementation(db, feature_id)


@router.get("/features/{feature_id}/dependencies", response_model=List[Dict[str, Any]])
async def get_feature_dependencies(
    feature_id: str,
    db: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    """Get direct dependencies for a feature."""
    return await GraphService.get_feature_dependencies(db, feature_id)
