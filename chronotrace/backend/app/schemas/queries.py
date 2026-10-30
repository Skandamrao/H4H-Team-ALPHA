"""
ChronoTrace AI — QA, Timeline, Historical State + Temporal Knowledge Graph Schemas
"""
from __future__ import annotations

from datetime import date
from typing import Optional, Literal, Dict, Any, List
from pydantic import BaseModel, Field

from app.schemas.events import TemporalEventOut, FeatureOut


ANSWER_STATUS = Literal[
    "SUPPORTED", "PARTIALLY_SUPPORTED", "CONFLICTED", "INSUFFICIENT_EVIDENCE"
]

RELATIONSHIP_TYPE = Literal[
    "PROPOSES", "APPROVES", "REJECTS", "IMPLEMENTS", "EXPLAINS_CHANGE",
    "RENAMES", "MODIFIES", "REMOVES", "DEPENDS_ON", "SUPERSEDES", "CONTRADICTS"
]


# ---------------------------------------------------------------------------
# QA Schemas
# ---------------------------------------------------------------------------

class QuestionRequest(BaseModel):
    question: str = Field(..., min_length=5)
    project_id: str
    as_of_event_date: Optional[date] = None       # temporal filter: event date cutoff
    as_of_ingestion_date: Optional[date] = None   # bitemporal knowledge cutoff


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
    cited_source_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    question_type: Optional[str] = None
    identified_features: list[str] = Field(default_factory=list)
    temporal_constraint: Optional[str] = None


# ---------------------------------------------------------------------------
# Timeline Schemas
# ---------------------------------------------------------------------------

class TimelineRequest(BaseModel):
    feature_id: str
    as_of_event_date: Optional[date] = None
    as_of_ingestion_date: Optional[date] = None


class TimelineEvent(BaseModel):
    event: TemporalEventOut
    milestone_label: Optional[str] = None
    order_uncertain: bool = False
    sequence_ambiguous: bool = False


class FeatureTimeline(BaseModel):
    feature: FeatureOut
    events: list[TimelineEvent] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    as_of_event_date: Optional[date] = None
    as_of_ingestion_date: Optional[date] = None


class ProjectTimelineOut(BaseModel):
    project_id: str
    events: list[TimelineEvent] = Field(default_factory=list)
    total_events: int = 0
    as_of_event_date: Optional[date] = None
    as_of_ingestion_date: Optional[date] = None


# ---------------------------------------------------------------------------
# Historical State Reconstruction Schemas (P07 Requirement D)
# ---------------------------------------------------------------------------

class FeatureStateOut(BaseModel):
    feature_id: str
    canonical_name: str
    active_name: str
    as_of_event_date: Optional[date] = None
    as_of_ingestion_date: Optional[date] = None
    is_proposed: bool = False
    is_approved: bool = False
    is_rejected: bool = False
    is_implemented: bool = False
    is_removed: bool = False
    was_implemented: bool = False
    is_reintroduced: bool = False
    modifications_count: int = 0
    active_aliases: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    supporting_event_ids: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class ProjectHistoricalStateOut(BaseModel):
    project_id: str
    as_of_event_date: Optional[date] = None
    as_of_ingestion_date: Optional[date] = None
    total_features: int
    features: list[FeatureStateOut] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Temporal Knowledge Graph Schemas (P07 Requirement A & F)
# ---------------------------------------------------------------------------

class GraphNode(BaseModel):
    id: str
    label: str
    type: Literal["feature", "event", "source", "decision"]
    data: Dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    relationship_type: str
    description: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict)


class TemporalGraphOut(BaseModel):
    project_id: str
    as_of_event_date: Optional[date] = None
    as_of_ingestion_date: Optional[date] = None
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
