"""
ChronoTrace AI — Pydantic Schemas for Events + Features
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field, model_validator


EVENT_TYPE = Literal[
    "PROPOSED", "APPROVED", "REJECTED", "IMPLEMENTED",
    "MODIFIED", "RENAMED", "REMOVED", "DEPENDENCY_ADDED", "OTHER",
]
DATE_PRECISION = Literal["exact", "approximate", "month", "quarter", "year", "unknown"]
DATE_BASIS = Literal["explicit", "inferred_context", "inferred_sequence", "unknown"]


# ---------------------------------------------------------------------------
# Feature schemas
# ---------------------------------------------------------------------------

class FeatureAliasOut(BaseModel):
    id: str
    alias: str
    source_id: str
    evidence_excerpt: str
    added_at: datetime

    model_config = {"from_attributes": True}


class FeatureOut(BaseModel):
    id: str
    project_id: str
    canonical_name: str
    created_at: datetime
    is_removed: bool
    is_implemented: bool
    is_approved: bool
    aliases: list[FeatureAliasOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Temporal Event schemas
# ---------------------------------------------------------------------------

class TemporalEventOut(BaseModel):
    id: str
    project_id: str
    feature_id: Optional[str] = None
    unresolved_feature_mention: Optional[str] = None
    event_type: EVENT_TYPE
    description: str
    previous_name: Optional[str] = None
    new_name: Optional[str] = None

    # Rule C — three distinct date fields
    event_date: Optional[date] = None
    event_date_raw: Optional[str] = None
    event_date_precision: DATE_PRECISION = "unknown"
    event_date_basis: DATE_BASIS = "unknown"

    # Rule H — provenance
    source_id: str
    evidence_excerpt: str
    actor: Optional[str] = None
    related_event_ids: list[str] = Field(default_factory=list)

    supersedes_event_id: Optional[str] = None
    is_superseded: bool = False
    extraction_confidence: Optional[float] = None
    needs_review: bool = False
    ingestion_timestamp: datetime

    model_config = {"from_attributes": True}


class TemporalEventCreate(BaseModel):
    """Used internally when the extraction service creates events."""
    project_id: str
    feature_id: Optional[str] = None
    unresolved_feature_mention: Optional[str] = None
    event_type: EVENT_TYPE
    description: str
    previous_name: Optional[str] = None
    new_name: Optional[str] = None
    event_date: Optional[date] = None
    event_date_raw: Optional[str] = None
    event_date_precision: DATE_PRECISION = "unknown"
    event_date_basis: DATE_BASIS = "unknown"
    source_id: str
    evidence_excerpt: str
    actor: Optional[str] = None
    related_event_ids: list[str] = Field(default_factory=list)
    extraction_confidence: Optional[float] = None
    needs_review: bool = False

    @model_validator(mode="after")
    def rename_requires_both_names(self) -> "TemporalEventCreate":
        if self.event_type == "RENAMED":
            if not self.previous_name or not self.new_name:
                raise ValueError("RENAMED events require both previous_name and new_name")
        return self

    @model_validator(mode="after")
    def validate_compulsory_evidence(self) -> "TemporalEventCreate":
        if not self.evidence_excerpt or not self.evidence_excerpt.strip():
            raise ValueError("Rule H violation: evidence_excerpt is compulsory and cannot be empty")
        return self

    @model_validator(mode="after")
    def validate_rules_a_and_b(self) -> "TemporalEventCreate":
        excerpt_lower = self.evidence_excerpt.lower()
        if self.event_type == "IMPLEMENTED":
            approval_only_phrases = [
                "no implementation has started",
                "approval only",
                "never implemented",
                "still not approved",
                "not shipped",
                "pending approval",
            ]
            if any(phrase in excerpt_lower for phrase in approval_only_phrases):
                raise ValueError(
                    f"Rule A violation: event_type cannot be IMPLEMENTED when evidence states: '{self.evidence_excerpt}'"
                )

        if self.event_type == "APPROVED":
            non_approved_phrases = [
                "no decision made",
                "has not been approved",
                "not approved yet",
                "pending security review",
                "pending design review",
                "pending legal review",
                "no approval decision made",
            ]
            if any(phrase in excerpt_lower for phrase in non_approved_phrases):
                raise ValueError(
                    f"Rule B violation: event_type cannot be APPROVED when evidence indicates unapproved status: '{self.evidence_excerpt}'"
                )

        return self


# ---------------------------------------------------------------------------
# Conflict schema
# ---------------------------------------------------------------------------

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

