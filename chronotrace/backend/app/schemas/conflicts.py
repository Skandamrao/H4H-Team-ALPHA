"""
ChronoTrace AI — Conflict Schemas
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ConflictOut(BaseModel):
    id: str
    project_id: str
    event_id_a: str
    event_id_b: str
    conflict_type: str
    description: str
    detected_at: datetime
    resolved: bool

    model_config = {"from_attributes": True}


class ConflictResolveRequest(BaseModel):
    resolution_notes: Optional[str] = Field(None, description="Explanation or rationale for resolving this conflict")
