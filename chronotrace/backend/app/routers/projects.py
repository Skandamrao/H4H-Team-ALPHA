"""
Projects Router — /api/projects
Supports project creation, listing, and inspection.
"""
from __future__ import annotations

from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.db_models import Project
from app.schemas.projects import ProjectCreate, ProjectOut

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=List[ProjectOut])
async def list_projects(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> List[ProjectOut]:
    """
    List all registered project workspaces.
    """
    result = await db.execute(
        select(Project).order_by(Project.created_at.desc()).limit(limit).offset(offset)
    )
    return [ProjectOut.model_validate(p) for p in result.scalars().all()]


@router.post("", response_model=ProjectOut, status_code=201)
async def create_project(
    payload: ProjectCreate,
    db: AsyncSession = Depends(get_db),
) -> ProjectOut:
    """
    Create a new project workspace for data isolation.
    """
    existing = await db.execute(select(Project).where(Project.id == payload.id))
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail=f"Project with ID '{payload.id}' already exists")

    project = Project(
        id=payload.id,
        name=payload.name,
        description=payload.description,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return ProjectOut.model_validate(project)


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> ProjectOut:
    """
    Retrieve project details by unique identifier.
    """
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    return ProjectOut.model_validate(project)
