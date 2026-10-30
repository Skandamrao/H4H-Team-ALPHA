"""
ChronoTrace AI — ORM Models
Append-only historical record store adhering to Rules A through H.
Core invariant: no UPDATE on SourceRecord or TemporalEvent rows.
Corrections are modeled via explicit EventRelationship or supersedes_event_id.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, date
from typing import Optional, List

from sqlalchemy import (
    String, Text, DateTime, Date, Boolean, ForeignKey,
    Enum as SAEnum, JSON, Index, UniqueConstraint, CheckConstraint, Integer, Float,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uuid() -> str:
    return str(uuid.uuid4())

def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Projects  (Multi-tenant isolation)
# ---------------------------------------------------------------------------

class Project(Base):
    """
    Project workspace entity providing data isolation for features and events.
    """
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    # Relationships
    sources: Mapped[List["SourceRecord"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    features: Mapped[List["Feature"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    batches: Mapped[List["IngestionBatch"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    events: Mapped[List["TemporalEvent"]] = relationship(back_populates="project", cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# Ingestion Batches  (Batch provenance & rollback capability)
# ---------------------------------------------------------------------------

class IngestionBatch(Base):
    """
    Tracks discrete ingestion jobs for provenance, auditing, and incremental updates.
    """
    __tablename__ = "ingestion_batches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    batch_number: Mapped[Optional[int]] = mapped_column(Integer)
    records_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    events_extracted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="completed", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    project: Mapped["Project"] = relationship(back_populates="batches")
    sources: Mapped[List["SourceRecord"]] = relationship(back_populates="batch")


# ---------------------------------------------------------------------------
# Source Records  (immutable after creation — Rule D)
# ---------------------------------------------------------------------------

RECORD_TYPES = (
    "meeting_notes", "design_spec", "email_thread",
    "changelog", "decision_log", "ticket", "other",
)

class SourceRecord(Base):
    """
    Represents a raw ingested document (meeting notes, spec, email, etc.).
    Never mutated after creation.
    """
    __tablename__ = "source_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)

    # Record classification
    record_type: Mapped[str] = mapped_column(
        SAEnum(*RECORD_TYPES, name="record_type_enum"),
        nullable=False,
    )
    title: Mapped[Optional[str]] = mapped_column(String(512))

    # Dates — three separate fields (Rule C)
    source_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    source_date_raw: Mapped[Optional[str]] = mapped_column(String(128))   # original expression
    ingestion_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    # Raw content & provenance fingerprinting (Rule D & Idempotency)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[Optional[str]] = mapped_column(String(256))
    content_fingerprint: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    file_reference: Mapped[Optional[str]] = mapped_column(String(512))
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    # Batch tracking for incremental ingestion (Rule D / R10)
    batch_id: Mapped[Optional[str]] = mapped_column(ForeignKey("ingestion_batches.id"), index=True, nullable=True)

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="sources")
    batch: Mapped[Optional["IngestionBatch"]] = relationship(back_populates="sources")
    events: Mapped[List["TemporalEvent"]] = relationship(back_populates="source", lazy="selectin")
    evidence_items: Mapped[List["EventEvidence"]] = relationship(back_populates="source", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_source_project_date", "project_id", "source_date"),
    )


# ---------------------------------------------------------------------------
# Features  (canonical identity — Rule E)
# ---------------------------------------------------------------------------

class Feature(Base):
    """
    Canonical feature entity. Created on first evidence.
    Name changes are recorded as RENAMED TemporalEvents, not by mutating this row.
    """
    __tablename__ = "features"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    canonical_name: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    # Soft lifecycle flags — derived from events, stored for fast queries
    is_removed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_implemented: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    project: Mapped["Project"] = relationship(back_populates="features")
    aliases: Mapped[List["FeatureAlias"]] = relationship(back_populates="feature", lazy="selectin", cascade="all, delete-orphan")
    events: Mapped[List["TemporalEvent"]] = relationship(back_populates="feature", lazy="selectin")
    outgoing_relationships: Mapped[List["FeatureRelationship"]] = relationship(
        foreign_keys="FeatureRelationship.source_feature_id", back_populates="source_feature", cascade="all, delete-orphan"
    )
    incoming_relationships: Mapped[List["FeatureRelationship"]] = relationship(
        foreign_keys="FeatureRelationship.target_feature_id", back_populates="target_feature", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("project_id", "canonical_name", name="uq_project_canonical_feature"),
    )


class FeatureAlias(Base):
    """
    Every name a feature has ever been known by, with its evidence source.
    Similarity alone NEVER creates an alias (Rule E).
    """
    __tablename__ = "feature_aliases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    feature_id: Mapped[str] = mapped_column(ForeignKey("features.id"), nullable=False, index=True)
    alias: Mapped[str] = mapped_column(String(512), nullable=False)
    source_id: Mapped[str] = mapped_column(ForeignKey("source_records.id"), nullable=False)
    evidence_excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    feature: Mapped["Feature"] = relationship(back_populates="aliases")

    __table_args__ = (
        UniqueConstraint("feature_id", "alias", name="uq_feature_alias"),
    )


# ---------------------------------------------------------------------------
# Feature Relationships  (Dependencies, Replacements, Sub-features)
# ---------------------------------------------------------------------------

class FeatureRelationship(Base):
    """
    Explicit relationships between software features (e.g. DEPENDS_ON, REPLACES).
    """
    __tablename__ = "feature_relationships"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    source_feature_id: Mapped[str] = mapped_column(ForeignKey("features.id"), nullable=False, index=True)
    target_feature_id: Mapped[str] = mapped_column(ForeignKey("features.id"), nullable=False, index=True)
    relationship_type: Mapped[str] = mapped_column(String(64), nullable=False)  # DEPENDS_ON, REPLACES, SUB_FEATURE_OF
    source_id: Mapped[Optional[str]] = mapped_column(ForeignKey("source_records.id"), nullable=True)
    evidence_excerpt: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    source_feature: Mapped["Feature"] = relationship(foreign_keys=[source_feature_id], back_populates="outgoing_relationships")
    target_feature: Mapped["Feature"] = relationship(foreign_keys=[target_feature_id], back_populates="incoming_relationships")


# ---------------------------------------------------------------------------
# Temporal Events  (append-only — Rule D, Rule H)
# ---------------------------------------------------------------------------

EVENT_TYPES = (
    "PROPOSED", "APPROVED", "REJECTED", "IMPLEMENTED",
    "MODIFIED", "RENAMED", "REMOVED", "DEPENDENCY_ADDED", "OTHER",
)

DATE_PRECISION = ("exact", "approximate", "month", "quarter", "year", "unknown")
DATE_BASIS = ("explicit", "inferred_context", "inferred_sequence", "unknown")


class TemporalEvent(Base):
    """
    A single historical event extracted from a source record.

    Critical invariants:
      - event_date is NEVER defaulted to the ingestion timestamp (Rule C).
      - Every event carries source_id + evidence_excerpt (Rule H).
      - Rows are never UPDATEd; corrections use supersedes_event_id (Rule D).
      - APPROVED != IMPLEMENTED; PROPOSED != APPROVED (Rules A, B).
    """
    __tablename__ = "temporal_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)

    # Feature linkage
    feature_id: Mapped[Optional[str]] = mapped_column(ForeignKey("features.id"), nullable=True, index=True)
    unresolved_feature_mention: Mapped[Optional[str]] = mapped_column(String(512))

    # Event classification
    event_type: Mapped[str] = mapped_column(
        SAEnum(*EVENT_TYPES, name="event_type_enum"), nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # Rename fields
    previous_name: Mapped[Optional[str]] = mapped_column(String(512))
    new_name: Mapped[Optional[str]] = mapped_column(String(512))

    # --- Three distinct date fields (Rule C) ---
    event_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    event_date_raw: Mapped[Optional[str]] = mapped_column(String(128))
    event_date_precision: Mapped[str] = mapped_column(
        SAEnum(*DATE_PRECISION, name="date_precision_enum"), default="unknown", nullable=False
    )
    event_date_basis: Mapped[str] = mapped_column(
        SAEnum(*DATE_BASIS, name="date_basis_enum"), default="unknown", nullable=False
    )

    # Source provenance (Rule H — compulsory)
    source_id: Mapped[str] = mapped_column(ForeignKey("source_records.id"), nullable=False, index=True)
    evidence_excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_offset_start: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    evidence_offset_end: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    actor: Mapped[Optional[str]] = mapped_column(String(256))

    # Related events (JSON array of event IDs)
    related_event_ids: Mapped[Optional[list]] = mapped_column(JSON, default=list)

    # Supersession chain (Rule D — corrections append, never overwrite)
    supersedes_event_id: Mapped[Optional[str]] = mapped_column(ForeignKey("temporal_events.id"), nullable=True)
    is_superseded: Mapped[bool] = mapped_column(Boolean, default=False, index=True, nullable=False)

    # Extraction metadata
    extraction_confidence: Mapped[Optional[float]] = mapped_column(Float)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Timestamps
    ingestion_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="events")
    source: Mapped["SourceRecord"] = relationship(back_populates="events")
    feature: Mapped[Optional["Feature"]] = relationship(back_populates="events")
    evidence_records: Mapped[List["EventEvidence"]] = relationship(back_populates="event", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_event_project_date", "project_id", "event_date"),
        Index("ix_event_feature_type", "feature_id", "event_type"),
    )


# ---------------------------------------------------------------------------
# Event Relationships  (Explicit graph edges between events)
# ---------------------------------------------------------------------------

class EventRelationship(Base):
    """
    Explicit causal, revision, or supersession relationship between two events.
    """
    __tablename__ = "event_relationships"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    from_event_id: Mapped[str] = mapped_column(ForeignKey("temporal_events.id"), nullable=False, index=True)
    to_event_id: Mapped[str] = mapped_column(ForeignKey("temporal_events.id"), nullable=False, index=True)
    relationship_type: Mapped[str] = mapped_column(String(64), nullable=False)  # SUPERSEDES, CAUSED_BY, DERIVED_FROM
    description: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    from_event: Mapped["TemporalEvent"] = relationship(foreign_keys=[from_event_id])
    to_event: Mapped["TemporalEvent"] = relationship(foreign_keys=[to_event_id])


# ---------------------------------------------------------------------------
# Event Evidence  (Direct quote and provenance tracking — Rule H)
# ---------------------------------------------------------------------------

class EventEvidence(Base):
    """
    Granular textual citation linking a temporal event directly to source text.
    """
    __tablename__ = "event_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    event_id: Mapped[str] = mapped_column(ForeignKey("temporal_events.id"), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("source_records.id"), nullable=False, index=True)
    exact_quote: Mapped[str] = mapped_column(Text, nullable=False)
    context_note: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    event: Mapped["TemporalEvent"] = relationship(back_populates="evidence_records")
    source: Mapped["SourceRecord"] = relationship(back_populates="evidence_items")


# ---------------------------------------------------------------------------
# Conflict Records
# ---------------------------------------------------------------------------

class ConflictRecord(Base):
    """
    Recorded when two events make genuinely incompatible claims about the
    same feature in the same time period (Rule F — progression is NOT conflict).
    """
    __tablename__ = "conflict_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    event_id_a: Mapped[str] = mapped_column(ForeignKey("temporal_events.id"), nullable=False)
    event_id_b: Mapped[str] = mapped_column(ForeignKey("temporal_events.id"), nullable=False)
    conflict_type: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    event_a: Mapped["TemporalEvent"] = relationship(foreign_keys=[event_id_a])
    event_b: Mapped["TemporalEvent"] = relationship(foreign_keys=[event_id_b])
