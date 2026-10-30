"""
ChronoTrace AI — Ingestion Request/Response Schemas
"""
from __future__ import annotations

from datetime import date
from typing import Optional, Literal
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
    # Rule C: source_date is the document's own date, NOT ingestion time
    source_date: Optional[date] = None
    source_date_raw: Optional[str] = None
    content: str = Field(..., min_length=1)
    author: Optional[str] = None
    batch_id: Optional[str] = None


class IngestBatchRequest(BaseModel):
    """Batch ingestion payload."""
    records: list[SourceRecordIn] = Field(..., min_length=1)


class IngestRecordResult(BaseModel):
    source_id: str
    events_extracted: int
    features_identified: int
    conflicts_detected: int
    warnings: list[str] = Field(default_factory=list)


class IngestBatchResponse(BaseModel):
    batch_id: str
    records_processed: int
    total_events_extracted: int
    total_features_identified: int
    total_conflicts_detected: int
    results: list[IngestRecordResult]
    warnings: list[str] = Field(default_factory=list)

