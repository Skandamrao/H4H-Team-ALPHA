"""
Dashboard Router — /api/dashboard
Aggregated project health, statistics, and temporal metrics.
"""
from __future__ import annotations

from typing import Dict, Any
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.db_models import (
    Feature, TemporalEvent, SourceRecord, IngestionBatch,
    ConflictRecord, EventRelationship, FeatureRelationship
)
from app.schemas.dashboard import DashboardMetricsOut

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/metrics", response_model=DashboardMetricsOut)
async def get_dashboard_metrics(
    project_id: str = Query(..., description="Project workspace ID"),
    db: AsyncSession = Depends(get_db),
) -> DashboardMetricsOut:
    """
    Retrieve aggregated dashboard statistics for a project workspace.
    """
    # 1. Total features
    f_total_res = await db.execute(
        select(func.count(Feature.id)).where(Feature.project_id == project_id)
    )
    total_features = f_total_res.scalar_one() or 0

    # 2. Implemented, approved, removed counts
    f_impl_res = await db.execute(
        select(func.count(Feature.id)).where(
            and_(Feature.project_id == project_id, Feature.is_implemented == True)
        )
    )
    implemented_features = f_impl_res.scalar_one() or 0

    f_appr_res = await db.execute(
        select(func.count(Feature.id)).where(
            and_(Feature.project_id == project_id, Feature.is_approved == True)
        )
    )
    approved_features = f_appr_res.scalar_one() or 0

    f_rem_res = await db.execute(
        select(func.count(Feature.id)).where(
            and_(Feature.project_id == project_id, Feature.is_removed == True)
        )
    )
    removed_features = f_rem_res.scalar_one() or 0

    # 3. Total events
    ev_total_res = await db.execute(
        select(func.count(TemporalEvent.id)).where(TemporalEvent.project_id == project_id)
    )
    total_events = ev_total_res.scalar_one() or 0

    # 4. Total sources
    src_total_res = await db.execute(
        select(func.count(SourceRecord.id)).where(SourceRecord.project_id == project_id)
    )
    total_sources = src_total_res.scalar_one() or 0

    # 5. Total batches
    b_total_res = await db.execute(
        select(func.count(IngestionBatch.id)).where(IngestionBatch.project_id == project_id)
    )
    total_batches = b_total_res.scalar_one() or 0

    # 6. Active conflicts
    conf_res = await db.execute(
        select(func.count(ConflictRecord.id)).where(
            and_(ConflictRecord.project_id == project_id, ConflictRecord.resolved == False)
        )
    )
    active_conflicts = conf_res.scalar_one() or 0

    # 7. Total relationships
    er_res = await db.execute(
        select(func.count(EventRelationship.id)).where(EventRelationship.project_id == project_id)
    )
    fr_res = await db.execute(
        select(func.count(FeatureRelationship.id)).where(FeatureRelationship.project_id == project_id)
    )
    total_relationships = (er_res.scalar_one() or 0) + (fr_res.scalar_one() or 0)

    # 8. Event type distribution
    dist_res = await db.execute(
        select(TemporalEvent.event_type, func.count(TemporalEvent.id))
        .where(TemporalEvent.project_id == project_id)
        .group_by(TemporalEvent.event_type)
    )
    event_type_distribution = {row[0]: row[1] for row in dist_res.all()}

    # 9. Recent events
    recent_res = await db.execute(
        select(TemporalEvent)
        .where(TemporalEvent.project_id == project_id)
        .order_by(TemporalEvent.event_date.desc().nullslast(), TemporalEvent.ingestion_timestamp.desc())
        .limit(10)
    )
    recent_events = [
        {
            "id": ev.id,
            "event_type": ev.event_type,
            "feature": ev.unresolved_feature_mention,
            "event_date": str(ev.event_date) if ev.event_date else None,
            "description": ev.description,
            "actor": ev.actor,
        }
        for ev in recent_res.scalars().all()
    ]

    return DashboardMetricsOut(
        project_id=project_id,
        total_features=total_features,
        total_events=total_events,
        total_sources=total_sources,
        total_batches=total_batches,
        active_conflicts=active_conflicts,
        implemented_features=implemented_features,
        approved_features=approved_features,
        removed_features=removed_features,
        total_relationships=total_relationships,
        event_type_distribution=event_type_distribution,
        recent_events=recent_events,
    )
