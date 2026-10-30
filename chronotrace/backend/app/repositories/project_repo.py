"""
Repository functions for Project and IngestionBatch entities.
"""
from __future__ import annotations

import uuid
from typing import Optional, List
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.db_models import Project, IngestionBatch

def _now() -> datetime:
    return datetime.now(timezone.utc)

class ProjectRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, project_id: str) -> Optional[Project]:
        result = await self.db.execute(select(Project).where(Project.id == project_id))
        return result.scalars().first()

    async def create_project(self, project_id: str, name: str, description: Optional[str] = None) -> Project:
        project = Project(
            id=project_id,
            name=name,
            description=description,
            created_at=_now(),
        )
        self.db.add(project)
        await self.db.flush()
        return project

    async def ensure_project(self, project_id: str, name: Optional[str] = None) -> Project:
        existing = await self.get_by_id(project_id)
        if existing:
            return existing
        return await self.create_project(project_id, name or project_id)

    async def create_batch(
        self,
        batch_id: str,
        project_id: str,
        records_count: int = 0,
        notes: Optional[str] = None,
    ) -> IngestionBatch:
        batch = IngestionBatch(
            id=batch_id,
            project_id=project_id,
            records_count=records_count,
            status="pending",
            created_at=_now(),
            notes=notes,
        )
        self.db.add(batch)
        await self.db.flush()
        return batch

    async def list_projects(self) -> List[Project]:
        result = await self.db.execute(select(Project).order_by(Project.created_at.desc()))
        return list(result.scalars().all())
