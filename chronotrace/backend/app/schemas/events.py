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
    is_valid: bool = True
    validity_reason: Optional[str] = None

    model_config = {"from_attributes": True}


class FeatureOut(BaseModel):
    id: str
    project_id: str
    canonical_name: str
    description: Optional[str] = None
    creation_source_id: Optional[str] = None
    creation_evidence_excerpt: Optional[str] = None
    identity_review_status: str = "CONFIRMED"
    created_at: datetime
    is_removed: bool
    is_implemented: bool
    is_approved: bool
    aliases: list[FeatureAliasOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Identity Resolution schemas (P06)
# ---------------------------------------------------------------------------

RESOLUTION_STATUS = Literal[
    "RESOLVED_EXACT_ID",
    "RESOLVED_CANONICAL",
    "RESOLVED_ALIAS",
    "RESOLVED_RENAME",
    "AMBIGUOUS_CANDIDATES",
    "NEW_FEATURE_CREATED",
    "UNRESOLVED",
]


class ResolutionResult(BaseModel):
    """
    Outcome of resolving a feature mention to a canonical Feature.

    status values:
      RESOLVED_EXACT_ID      — explicit canonical feature ID was provided and valid.
      RESOLVED_CANONICAL     — exact canonical name match (case-insensitive).
      RESOLVED_ALIAS         — exact known alias match.
      RESOLVED_RENAME        — matched via explicit rename evidence / rename chain.
      AMBIGUOUS_CANDIDATES   — multiple candidate features matched; Rule E prevents auto-merge.
      NEW_FEATURE_CREATED    — no match found; a new feature was created (only if allow_new=True).
      UNRESOLVED             — no match found and allow_new=False; nothing was created.
    """
    feature_id: Optional[str] = None
    status: RESOLUTION_STATUS
    candidate_ids: list[str] = Field(default_factory=list)
    uncertainty_reason: Optional[str] = None
    confidence_score: float = 1.0
    matched_by: Optional[str] = None
    is_ambiguous: bool = False
    unresolved_record_id: Optional[str] = None
    created_new_feature: bool = False


class UnresolvedIdentityOut(BaseModel):
    id: str
    project_id: str
    mention: str
    source_id: str
    evidence_excerpt: str
    candidate_feature_ids: list[str] = Field(default_factory=list)
    uncertainty_reason: str
    status: str
    resolved_feature_id: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ResolveAmbiguityIn(BaseModel):
    """Request to manually resolve an ambiguous/unresolved feature mention."""
    unresolved_id: str
    target_feature_id: Optional[str] = None
    new_feature_name: Optional[str] = None
    new_feature_description: Optional[str] = None
    notes: Optional[str] = None


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
    evidence_offset_start: Optional[int] = None
    evidence_offset_end: Optional[int] = None
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
    evidence_offset_start: Optional[int] = None
    evidence_offset_end: Optional[int] = None
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

