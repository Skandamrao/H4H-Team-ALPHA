"""
ChronoTrace AI — Dashboard Metrics Schemas
"""
from __future__ import annotations

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class DashboardMetricsOut(BaseModel):
    project_id: str
    total_features: int = 0
    total_events: int = 0
    total_sources: int = 0
    total_batches: int = 0
    active_conflicts: int = 0
    implemented_features: int = 0
    approved_features: int = 0
    removed_features: int = 0
    total_relationships: int = 0
    event_type_distribution: Dict[str, int] = Field(default_factory=dict)
    recent_events: List[Dict[str, Any]] = Field(default_factory=list)
