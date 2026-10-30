"""
ChronoTrace AI — Project Schemas
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    id: str = Field(..., min_length=1, max_length=128, description="Unique slug or identifier for the project")
    name: str = Field(..., min_length=1, max_length=256, description="Human-readable project name")
    description: Optional[str] = Field(None, description="Optional description of the software project")


class ProjectOut(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}
