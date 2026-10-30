"""
Pydantic schemas for ChronoGraph AI API requests and responses.

Strict validation is applied everywhere — no raw AI output is
accepted without passing through these schemas first.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional, Any

from pydantic import BaseModel, Field, field_validator


# ── Enumerations ──────────────────────────────────────────────────────────────

class EventType(str, Enum):
    FEATURE_INTRODUCED = "FEATURE_INTRODUCED"
    FEATURE_MODIFIED = "FEATURE_MODIFIED"
    FEATURE_RENAMED = "FEATURE_RENAMED"
    FEATURE_REMOVED = "FEATURE_REMOVED"
    DECISION_PROPOSED = "DECISION_PROPOSED"
    DECISION_APPROVED = "DECISION_APPROVED"
    DECISION_REJECTED = "DECISION_REJECTED"
    FEATURE_IMPLEMENTED = "FEATURE_IMPLEMENTED"
    FEATURE_DEPRECATED = "FEATURE_DEPRECATED"
    MODULE_CREATED = "MODULE_CREATED"
    MODULE_MODIFIED = "MODULE_MODIFIED"


class DecisionStatus(str, Enum):
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    IMPLEMENTED = "IMPLEMENTED"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"


class DateConfidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class ProcessingStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class FeatureStatus(str, Enum):
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"
    REMOVED = "REMOVED"
    PROPOSED = "PROPOSED"
    UNKNOWN = "UNKNOWN"


# ── AI Extraction Schemas ─────────────────────────────────────────────────────

class ExtractedEvent(BaseModel):
    """Schema for a single event extracted by the AI service.
    This is the contract between the AI output and the application.
    """
    title: str = Field(..., min_length=1, max_length=512)
    description: str = Field(default="")
    event_type: EventType
    feature_name: Optional[str] = None
    module_name: Optional[str] = None
    related_features: List[str] = Field(default_factory=list)
    decision: Optional[str] = None
    reason: Optional[str] = None
    event_date: Optional[str] = None           # ISO 8601 string; null if unknown
    event_date_confidence: DateConfidence = DateConfidence.UNKNOWN
    decision_status: Optional[DecisionStatus] = None
    responsible_person: Optional[str] = None
    supporting_text: str = Field(default="")   # Verbatim excerpt from source
    confidence_score: float = Field(default=0.5, ge=0.0, le=1.0)

    @field_validator("event_date", mode="before")
    @classmethod
    def empty_string_to_none(cls, v: Any) -> Optional[str]:
        if v == "" or v is None:
            return None
        return v

    @field_validator("related_features", mode="before")
    @classmethod
    def none_to_list(cls, v: Any) -> List[str]:
        if v is None:
            return []
        return v


class ExtractionResult(BaseModel):
    """Full result returned by the AI extraction service for one document."""
    document_id: str
    events: List[ExtractedEvent] = Field(default_factory=list)
    extraction_errors: List[str] = Field(default_factory=list)
    raw_response: Optional[str] = None


# ── Document Schemas ──────────────────────────────────────────────────────────

class DocumentResponse(BaseModel):
    id: str
    filename: str
    original_filename: str
    file_type: str
    file_size_bytes: int
    document_date: Optional[datetime]
    document_date_confidence: str
    ingested_at: datetime
    processing_status: str
    processing_error: Optional[str]
    page_count: Optional[int]
    is_duplicate: bool
    event_count: int = 0

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    total: int
    documents: List[DocumentResponse]


# ── Feature Schemas ───────────────────────────────────────────────────────────

class FeatureAliasResponse(BaseModel):
    id: str
    alias: str
    is_canonical: bool
    added_at: datetime

    model_config = {"from_attributes": True}


class FeatureResponse(BaseModel):
    id: str
    canonical_name: str
    current_status: str
    first_seen_date: Optional[datetime]
    last_event_date: Optional[datetime]
    module_name: Optional[str] = None
    aliases: List[FeatureAliasResponse] = []
    event_count: int = 0

    model_config = {"from_attributes": True}


class FeatureListResponse(BaseModel):
    total: int
    features: List[FeatureResponse]


# ── Event Schemas ─────────────────────────────────────────────────────────────

class EvidenceResponse(BaseModel):
    id: str
    document_id: str
    document_filename: str
    excerpt: str
    confidence: float

    model_config = {"from_attributes": True}


class EventResponse(BaseModel):
    id: str
    title: str
    description: Optional[str]
    event_type: str
    decision_status: Optional[str]
    feature_name: Optional[str] = None
    feature_name_in_source: Optional[str]
    module_name: Optional[str]
    reason: Optional[str]
    decision_text: Optional[str]
    supporting_text: Optional[str]
    event_date: Optional[datetime]
    event_date_confidence: str
    recorded_at: datetime
    confidence_score: float
    has_conflict: bool
    source_document_id: Optional[str]
    source_document_filename: Optional[str] = None
    evidence: List[EvidenceResponse] = []

    model_config = {"from_attributes": True}


class EventListResponse(BaseModel):
    total: int
    events: List[EventResponse]


# ── Timeline Schemas ──────────────────────────────────────────────────────────

class TimelineEventResponse(BaseModel):
    event_id: str
    title: str
    event_type: str
    decision_status: Optional[str]
    event_date: Optional[datetime]
    event_date_confidence: str
    description: Optional[str]
    reason: Optional[str]
    source_document_filename: Optional[str]
    confidence_score: float
    has_conflict: bool
    evidence: List[EvidenceResponse] = []


class TimelineResponse(BaseModel):
    feature_id: str
    feature_name: str
    aliases: List[str] = []
    events: List[TimelineEventResponse] = []


# ── Knowledge Graph Schemas ───────────────────────────────────────────────────

class GraphNode(BaseModel):
    id: str
    label: str
    node_type: str          # feature | module | event | decision | document | person
    properties: dict = {}


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    relationship_type: str
    properties: dict = {}


class GraphResponse(BaseModel):
    nodes: List[GraphNode] = []
    edges: List[GraphEdge] = []


# ── AI Assistant Schemas ──────────────────────────────────────────────────────

class AssistantQuery(BaseModel):
    question: str = Field(..., min_length=3, max_length=1000)
    project_id: Optional[str] = None


class Citation(BaseModel):
    document_filename: str
    document_id: str
    excerpt: Optional[str] = None


class AssistantAnswer(BaseModel):
    question: str
    answer: str
    historical_events: List[dict] = []
    supporting_evidence: List[Citation] = []
    confidence: str        # High | Medium | Low | Insufficient
    has_conflicts: bool = False
    conflict_note: Optional[str] = None
    missing_information: Optional[str] = None


# ── Ingestion Schemas ─────────────────────────────────────────────────────────

class IngestionBatchResponse(BaseModel):
    id: str
    label: Optional[str]
    started_at: datetime
    completed_at: Optional[datetime]
    status: str
    total_files: int
    processed_files: int
    failed_files: int
    duplicate_files: int
    new_events_extracted: int

    model_config = {"from_attributes": True}


# ── Dashboard Schemas ─────────────────────────────────────────────────────────

class DashboardStats(BaseModel):
    total_documents: int
    total_events: int
    total_features: int
    total_decisions: int
    total_conflicts: int
    recent_batches: List[IngestionBatchResponse] = []
    event_type_distribution: List[dict] = []
    feature_activity: List[dict] = []


# ── Conflict Schemas ──────────────────────────────────────────────────────────

class ConflictRecord(BaseModel):
    feature_id: str
    feature_name: str
    conflict_type: str      # DATE_CONFLICT | STATUS_CONFLICT | DECISION_CONFLICT
    event_a: EventResponse
    event_b: EventResponse
    description: str


class ConflictListResponse(BaseModel):
    total: int
    conflicts: List[ConflictRecord]

