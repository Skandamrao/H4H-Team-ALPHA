"""Feature management and exploration routes."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.database import get_db
from app.models.models import Feature, FeatureAlias, Event
from app.schemas.schemas import FeatureResponse, FeatureListResponse, FeatureAliasResponse

router = APIRouter()


def _build_feature_response(feature: Feature, db: Session) -> FeatureResponse:
    event_count = db.query(func.count(Event.id)).filter(Event.feature_id == feature.id).scalar() or 0
    aliases = [
        FeatureAliasResponse(id=a.id, alias=a.alias, is_canonical=a.is_canonical, added_at=a.added_at)
        for a in feature.aliases
    ]
    module_name = feature.module.canonical_name if feature.module else None
    return FeatureResponse(
        id=feature.id,
        canonical_name=feature.canonical_name,
        current_status=feature.current_status,
        first_seen_date=feature.first_seen_date,
        last_event_date=feature.last_event_date,
        module_name=module_name,
        aliases=aliases,
        event_count=event_count,
    )


@router.get("/", response_model=FeatureListResponse)
def list_features(
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(Feature)
    if isinstance(status, str) and status:
        query = query.filter(Feature.current_status == status)
    total = query.count()
    features = query.order_by(Feature.canonical_name).offset(skip).limit(limit).all()
    return FeatureListResponse(total=total, features=[_build_feature_response(f, db) for f in features])


@router.get("/{feature_id}", response_model=FeatureResponse)
def get_feature(feature_id: str, db: Session = Depends(get_db)):
    feature = db.get(Feature, feature_id)
    if not feature:
        raise HTTPException(status_code=404, detail="Feature not found.")
    return _build_feature_response(feature, db)
