"""
ChronoTrace AI — QA + Timeline Query Schemas
"""
from __future__ import annotations

from datetime import date
from typing import Optional, Literal
from pydantic import BaseModel, Field

from app.schemas.events import TemporalEventOut, FeatureOut


ANSWER_STATUS = Literal[
    "SUPPORTED", "PARTIALLY_SUPPORTED", "CONFLICTED", "INSUFFICIENT_EVIDENCE"
]


# ---------------------------------------------------------------------------
# QA
# ---------------------------------------------------------------------------

class QuestionRequest(BaseModel):
    question: str = Field(..., min_length=5)
    project_id: str
    as_of_event_date: Optional[date] = None       # temporal filter: event date cutoff
    as_of_ingestion_date: Optional[date] = None   # knowledge cutoff


class SupportingEvidence(BaseModel):
    event: TemporalEventOut
    relevance_note: str


class QuestionAnswer(BaseModel):
    question: str
    answer: str
    status: ANSWER_STATUS
    supporting_evidence: list[SupportingEvidence] = Field(default_factory=list)
    conflicting_events: list[TemporalEventOut] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    # Rule H: every answer cites source IDs
    cited_source_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------

class TimelineRequest(BaseModel):
    feature_id: str
    as_of_event_date: Optional[date] = None


class TimelineEvent(BaseModel):
    event: TemporalEventOut
    milestone_label: Optional[str] = None   # e.g. "First Proposed", "Approved", "Shipped"


class FeatureTimeline(BaseModel):
    feature: FeatureOut
    events: list[TimelineEvent] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    as_of_event_date: Optional[date] = None

