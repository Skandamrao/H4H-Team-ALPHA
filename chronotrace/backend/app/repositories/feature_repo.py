"""
Repository functions for Feature, FeatureAlias, and FeatureRelationship entities.
Enforces canonical identity rules (Rule E).
"""
from __future__ import annotations

import uuid
from typing import Optional, List
from datetime import datetime, timezone
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.db_models import Feature, FeatureAlias, FeatureRelationship

def _uuid() -> str:
    return str(uuid.uuid4())

def _now() -> datetime:
    return datetime.now(timezone.utc)

class FeatureRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, feature_id: str) -> Optional[Feature]:
        result = await self.db.execute(select(Feature).where(Feature.id == feature_id))
        return result.scalars().first()

    async def get_by_canonical_name(self, project_id: str, name: str) -> Optional[Feature]:
        result = await self.db.execute(
            select(Feature).where(
                Feature.project_id == project_id,
                Feature.canonical_name == name.strip(),
            )
        )
        return result.scalars().first()

    async def create_feature(self, project_id: str, canonical_name: str) -> Feature:
        feat = Feature(
            id=_uuid(),
            project_id=project_id,
            canonical_name=canonical_name.strip(),
            created_at=_now(),
        )
        self.db.add(feat)
        await self.db.flush()
        return feat

    async def add_alias(
        self,
        feature_id: str,
        alias: str,
        source_id: str,
        evidence_excerpt: str,
    ) -> FeatureAlias:
        existing = await self.db.execute(
            select(FeatureAlias).where(
                FeatureAlias.feature_id == feature_id,
                FeatureAlias.alias == alias.strip(),
            )
        )
        found = existing.scalars().first()
        if found:
            return found

        alias_obj = FeatureAlias(
            id=_uuid(),
            feature_id=feature_id,
            alias=alias.strip(),
            source_id=source_id,
            evidence_excerpt=evidence_excerpt,
            added_at=_now(),
        )
        self.db.add(alias_obj)
        await self.db.flush()
        return alias_obj

    async def link_features(
        self,
        project_id: str,
        source_feature_id: str,
        target_feature_id: str,
        relationship_type: str,
        source_id: Optional[str] = None,
        evidence_excerpt: Optional[str] = None,
    ) -> FeatureRelationship:
        rel = FeatureRelationship(
            id=_uuid(),
            project_id=project_id,
            source_feature_id=source_feature_id,
            target_feature_id=target_feature_id,
            relationship_type=relationship_type,
            source_id=source_id,
            evidence_excerpt=evidence_excerpt,
            created_at=_now(),
        )
        self.db.add(rel)
        await self.db.flush()
        return rel

    async def list_features(self, project_id: str) -> List[Feature]:
        result = await self.db.execute(
            select(Feature).where(Feature.project_id == project_id).order_by(Feature.canonical_name.asc())
        )
        return list(result.scalars().all())
