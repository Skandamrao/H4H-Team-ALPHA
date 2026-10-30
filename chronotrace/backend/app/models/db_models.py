"""
ChronoTrace AI — ORM Models
Append-only historical record store. Core invariant: no UPDATE on Source or
TemporalEvent rows. Corrections are new rows with a supersedes_event_id FK.
"""
from __future__ import annotations

import uuid
from datetime import datetime, date
from typing import Optional

from sqlalchemy import (
    String, Text, DateTime, Date, Boolean, ForeignKey,
    Enum as SAEnum, JSON, Index, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uuid() -> str:
    return str(uuid.uuid4())

def _now() -> datetime:
    return datetime.utcnow()


# ---------------------------------------------------------------------------
# Source Records  (immutable after creation — Rule D)
# ---------------------------------------------------------------------------

class SourceRecord(Base):
    """
    Represents a raw ingested document (meeting notes, spec, email, etc.).
    Never mutated after creation.
    """
    __tablename__ = "source_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    # Record classification
    record_type: Mapped[str] = mapped_column(
        SAEnum(
            "meeting_notes", "design_spec", "email_thread",
            "changelog", "decision_log", "ticket", "other",
            name="record_type_enum",
        ),
        nullable=False,
    )
    title: Mapped[Optional[str]] = mapped_column(String(512))

    # Dates — three separate fields (Rule C)
    source_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    source_date_raw: Mapped[Optional[str]] = mapped_column(String(128))   # original expression
    ingestion_timestamp: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)

    # Raw content
    content: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[Optional[str]] = mapped_column(String(256))

    # Batch tracking for incremental ingestion (Rule D / R10)
    batch_id: Mapped[Optional[str]] = mapped_column(String(36), index=True)

    # Relationships
    events: Mapped[list["TemporalEvent"]] = relationship(
        back_populates="source", lazy="selectin"
    )

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
    project_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    canonical_name: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    # Soft lifecycle flags — derived from events, stored for fast queries
    is_removed: Mapped[bool] = mapped_column(Boolean, default=False)
    is_implemented: Mapped[bool] = mapped_column(Boolean, default=False)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False)

    aliases: Mapped[list["FeatureAlias"]] = relationship(
        back_populates="feature", lazy="selectin"
    )
    events: Mapped[list["TemporalEvent"]] = relationship(
        back_populates="feature", lazy="selectin"
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
    added_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    feature: Mapped["Feature"] = relationship(back_populates="aliases")

    __table_args__ = (
        UniqueConstraint("feature_id", "alias", name="uq_feature_alias"),
    )


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
      - APPROVED ≠ IMPLEMENTED; PROPOSED ≠ APPROVED (Rules A, B).
    """
    __tablename__ = "temporal_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    # Feature linkage — may be null if extraction found no canonical match (Rule E)
    feature_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("features.id"), nullable=True, index=True
    )
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
        SAEnum(*DATE_PRECISION, name="date_precision_enum"), default="unknown"
    )
    event_date_basis: Mapped[str] = mapped_column(
        SAEnum(*DATE_BASIS, name="date_basis_enum"), default="unknown"
    )

    # Source provenance (Rule H — compulsory)
    source_id: Mapped[str] = mapped_column(
        ForeignKey("source_records.id"), nullable=False, index=True
    )
    evidence_excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[Optional[str]] = mapped_column(String(256))

    # Related events (JSON array of event IDs)
    related_event_ids: Mapped[Optional[list]] = mapped_column(JSON, default=list)

    # Supersession chain (Rule D — corrections append, never overwrite)
    supersedes_event_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("temporal_events.id"), nullable=True
    )
    is_superseded: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    # Extraction metadata
    extraction_confidence: Mapped[Optional[float]] = mapped_column()
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)

    # Timestamps
    ingestion_timestamp: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)

    # Relationships
    source: Mapped["SourceRecord"] = relationship(back_populates="events")
    feature: Mapped[Optional["Feature"]] = relationship(back_populates="events")

    __table_args__ = (
        Index("ix_event_project_date", "project_id", "event_date"),
        Index("ix_event_feature_type", "feature_id", "event_type"),
    )


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
    project_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_id_a: Mapped[str] = mapped_column(ForeignKey("temporal_events.id"), nullable=False)
    event_id_b: Mapped[str] = mapped_column(ForeignKey("temporal_events.id"), nullable=False)
    conflict_type: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)

