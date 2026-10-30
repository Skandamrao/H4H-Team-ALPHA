"""
ChronoTrace AI — Ingestion Request/Response Schemas
Strictly typed data transfer objects for document parsing and batch processing.
"""
from __future__ import annotations

from datetime import date
from typing import Optional, Literal, Dict, Any
from pydantic import BaseModel, Field


RECORD_TYPE = Literal[
    "meeting_notes", "design_spec", "email_thread",
    "changelog", "decision_log", "ticket", "other",
]


class SourceRecordIn(BaseModel):
    """A single document submitted for ingestion."""
    project_id: str = Field(..., min_length=1)
    record_type: RECORD_TYPE
    title: Optional[str] = None
    # Rule C: source_date is the document's own creation date, NOT ingestion time
    source_date: Optional[date] = None
    source_date_raw: Optional[str] = None
    content: str = Field(..., min_length=1)
    author: Optional[str] = None
    batch_id: Optional[str] = None
    file_reference: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class IngestBatchRequest(BaseModel):
    """Batch ingestion payload supporting initial vs incremental modes."""
    records: list[SourceRecordIn] = Field(..., min_length=1)
    mode: Literal["initial", "incremental"] = "incremental"
    batch_id: Optional[str] = None
    notes: Optional[str] = None


class IngestRecordResult(BaseModel):
    source_id: str
    status: Literal["success", "duplicate", "failed"] = "success"
    events_extracted: int = 0
    features_identified: int = 0
    conflicts_detected: int = 0
    warnings: list[str] = Field(default_factory=list)
    error: Optional[str] = None


class IngestBatchResponse(BaseModel):
    batch_id: str
    mode: str = "incremental"
    records_processed: int
    successful_records: int
    failed_records: int = 0
    duplicate_records: int = 0
    total_events_extracted: int
    total_features_identified: int
    total_conflicts_detected: int
    results: list[IngestRecordResult]
    warnings: list[str] = Field(default_factory=list)


class NormalizedSourceRecordOut(BaseModel):
    """Canonical representation of an ingested source record retrieved from DB."""
    id: str
    project_id: str
    record_type: str
    title: Optional[str] = None
    source_date: Optional[date] = None
    source_date_raw: Optional[str] = None
    author: Optional[str] = None
    content: str
    content_fingerprint: Optional[str] = None
    file_reference: Optional[str] = None
    metadata_json: Optional[Dict[str, Any]] = None
    ingestion_timestamp: Any
    batch_id: Optional[str] = None

    model_config = {"from_attributes": True}
