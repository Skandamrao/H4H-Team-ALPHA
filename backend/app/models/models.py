"""
SQLAlchemy ORM Models for ChronoGraph AI.

Tables:
  projects, documents, ingestion_batches, features, feature_aliases,
  modules, events, decisions, event_relationships, event_evidence, people

Design principles:
  - Every event preserves its original source reference.
  - Event dates and ingestion dates are stored independently.
  - History is never deleted; only superseded.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey,
    Integer, String, Text, UniqueConstraint, Index,
)
from sqlalchemy.orm import relationship

from app.db.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.utcnow()


# ── Projects ─────────────────────────────────────────────────────────────────

class Project(Base):
    __tablename__ = "projects"

    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(255), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_now, nullable=False)
    updated_at = Column(DateTime, default=_now, onupdate=_now, nullable=False)

    documents = relationship("Document", back_populates="project", cascade="all, delete-orphan")
    features = relationship("Feature", back_populates="project", cascade="all, delete-orphan")
    modules = relationship("Module", back_populates="project", cascade="all, delete-orphan")


# ── Ingestion Batches ─────────────────────────────────────────────────────────

class IngestionBatch(Base):
    __tablename__ = "ingestion_batches"

    id = Column(String(36), primary_key=True, default=_uuid)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True)
    label = Column(String(255), nullable=True)          # Human-friendly batch label
    started_at = Column(DateTime, default=_now, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    total_files = Column(Integer, default=0)
    processed_files = Column(Integer, default=0)
    failed_files = Column(Integer, default=0)
    duplicate_files = Column(Integer, default=0)
    new_events_extracted = Column(Integer, default=0)
    status = Column(String(50), default="PROCESSING")   # PROCESSING | COMPLETED | FAILED

    documents = relationship("Document", back_populates="ingestion_batch")


# ── Documents ─────────────────────────────────────────────────────────────────

class Document(Base):
    __tablename__ = "documents"

    id = Column(String(36), primary_key=True, default=_uuid)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True)
    ingestion_batch_id = Column(String(36), ForeignKey("ingestion_batches.id"), nullable=True)

    filename = Column(String(512), nullable=False)
    original_filename = Column(String(512), nullable=False)
    file_type = Column(String(20), nullable=False)      # pdf | txt | md | json
    file_size_bytes = Column(Integer, nullable=False)
    file_hash = Column(String(64), nullable=False)      # SHA-256 for duplicate detection

    # Date of the document content (extracted, may be null if unknown)
    document_date = Column(DateTime, nullable=True)
    document_date_confidence = Column(String(20), default="UNKNOWN")  # HIGH | MEDIUM | LOW | UNKNOWN

    # Ingestion metadata
    ingested_at = Column(DateTime, default=_now, nullable=False)
    processing_status = Column(String(30), default="PENDING")  # PENDING | PROCESSING | COMPLETED | FAILED
    processing_error = Column(Text, nullable=True)

    extracted_text = Column(Text, nullable=True)
    page_count = Column(Integer, nullable=True)
    is_duplicate = Column(Boolean, default=False, nullable=False)
    duplicate_of_id = Column(String(36), ForeignKey("documents.id"), nullable=True)

    __table_args__ = (
        Index("ix_documents_file_hash", "file_hash"),
        Index("ix_documents_project_id", "project_id"),
    )

    project = relationship("Project", back_populates="documents")
    ingestion_batch = relationship("IngestionBatch", back_populates="documents")
    events = relationship("Event", back_populates="source_document")
    evidence = relationship("EventEvidence", back_populates="document")


# ── Modules ───────────────────────────────────────────────────────────────────

class Module(Base):
    __tablename__ = "modules"

    id = Column(String(36), primary_key=True, default=_uuid)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True)
    name = Column(String(255), nullable=False)
    canonical_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_now, nullable=False)

    __table_args__ = (UniqueConstraint("project_id", "canonical_name", name="uq_module_project_name"),)

    project = relationship("Project", back_populates="modules")
    features = relationship("Feature", back_populates="module")


# ── Features ──────────────────────────────────────────────────────────────────

class Feature(Base):
    __tablename__ = "features"

    id = Column(String(36), primary_key=True, default=_uuid)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True)
    module_id = Column(String(36), ForeignKey("modules.id"), nullable=True)

    canonical_name = Column(String(255), nullable=False)
    current_status = Column(String(50), default="UNKNOWN")
    # ACTIVE | DEPRECATED | REMOVED | PROPOSED | UNKNOWN

    first_seen_date = Column(DateTime, nullable=True)
    last_event_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_now, nullable=False)
    updated_at = Column(DateTime, default=_now, onupdate=_now, nullable=False)

    __table_args__ = (
        Index("ix_features_canonical_name", "canonical_name"),
        Index("ix_features_project_id", "project_id"),
    )

    project = relationship("Project", back_populates="features")
    module = relationship("Module", back_populates="features")
    aliases = relationship("FeatureAlias", back_populates="feature", cascade="all, delete-orphan")
    events = relationship("Event", back_populates="feature")


# ── Feature Aliases ───────────────────────────────────────────────────────────

class FeatureAlias(Base):
    """Records every name a feature has been called, with its source."""
    __tablename__ = "feature_aliases"

    id = Column(String(36), primary_key=True, default=_uuid)
    feature_id = Column(String(36), ForeignKey("features.id"), nullable=False)
    alias = Column(String(255), nullable=False)
    source_document_id = Column(String(36), ForeignKey("documents.id"), nullable=True)
    added_at = Column(DateTime, default=_now, nullable=False)
    is_canonical = Column(Boolean, default=False)

    __table_args__ = (
        UniqueConstraint("feature_id", "alias", name="uq_feature_alias"),
        Index("ix_feature_aliases_alias", "alias"),
    )

    feature = relationship("Feature", back_populates="aliases")


# ── People ────────────────────────────────────────────────────────────────────

class Person(Base):
    __tablename__ = "people"

    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(255), nullable=False, unique=True)
    email = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=_now, nullable=False)

    events_responsible = relationship("Event", back_populates="responsible_person")


# ── Events ────────────────────────────────────────────────────────────────────

class Event(Base):
    """
    Core historical unit.  Every event is immutable once created.
    New events supersede old ones — old events are never deleted.
    """
    __tablename__ = "events"

    id = Column(String(36), primary_key=True, default=_uuid)
    feature_id = Column(String(36), ForeignKey("features.id"), nullable=True)
    source_document_id = Column(String(36), ForeignKey("documents.id"), nullable=True)
    responsible_person_id = Column(String(36), ForeignKey("people.id"), nullable=True)

    title = Column(String(512), nullable=False)
    description = Column(Text, nullable=True)

    # Event typing
    event_type = Column(String(50), nullable=False)
    # FEATURE_INTRODUCED | FEATURE_MODIFIED | FEATURE_RENAMED | FEATURE_REMOVED |
    # DECISION_PROPOSED | DECISION_APPROVED | DECISION_REJECTED |
    # FEATURE_IMPLEMENTED | FEATURE_DEPRECATED | MODULE_CREATED | MODULE_MODIFIED

    decision_status = Column(String(30), nullable=True)
    # PROPOSED | APPROVED | REJECTED | IMPLEMENTED | CANCELLED | UNKNOWN

    feature_name_in_source = Column(String(255), nullable=True)  # Original name used in document
    module_name = Column(String(255), nullable=True)
    related_feature_names = Column(Text, nullable=True)          # JSON list of strings
    decision_text = Column(Text, nullable=True)
    reason = Column(Text, nullable=True)
    supporting_text = Column(Text, nullable=True)                # Verbatim excerpt from source

    # Dates — critically separated
    event_date = Column(DateTime, nullable=True)                 # When the event occurred in the project
    event_date_confidence = Column(String(20), default="UNKNOWN")
    recorded_at = Column(DateTime, default=_now, nullable=False) # When we ingested this event

    confidence_score = Column(Float, default=0.5)               # 0.0 – 1.0

    # Conflict tracking
    has_conflict = Column(Boolean, default=False)
    conflict_note = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_events_feature_id", "feature_id"),
        Index("ix_events_event_type", "event_type"),
        Index("ix_events_event_date", "event_date"),
    )

    feature = relationship("Feature", back_populates="events")
    source_document = relationship("Document", back_populates="events")
    responsible_person = relationship("Person", back_populates="events_responsible")
    evidence = relationship("EventEvidence", back_populates="event", cascade="all, delete-orphan")
    outgoing_relationships = relationship(
        "EventRelationship",
        foreign_keys="EventRelationship.source_event_id",
        back_populates="source_event",
        cascade="all, delete-orphan",
    )
    incoming_relationships = relationship(
        "EventRelationship",
        foreign_keys="EventRelationship.target_event_id",
        back_populates="target_event",
    )


# ── Decisions ─────────────────────────────────────────────────────────────────

class Decision(Base):
    """A decision record linked to one or more events."""
    __tablename__ = "decisions"

    id = Column(String(36), primary_key=True, default=_uuid)
    event_id = Column(String(36), ForeignKey("events.id"), nullable=False)
    feature_id = Column(String(36), ForeignKey("features.id"), nullable=True)

    title = Column(String(512), nullable=False)
    decision_text = Column(Text, nullable=True)
    status = Column(String(30), default="PROPOSED")
    decided_at = Column(DateTime, nullable=True)
    decided_by = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=_now, nullable=False)

    event = relationship("Event")


# ── Event Relationships ───────────────────────────────────────────────────────

class EventRelationship(Base):
    """
    Directed edge between two events.
    Relationship types: FOLLOWS | SUPERSEDES | CAUSED_BY | REVERSES
    """
    __tablename__ = "event_relationships"

    id = Column(String(36), primary_key=True, default=_uuid)
    source_event_id = Column(String(36), ForeignKey("events.id"), nullable=False)
    target_event_id = Column(String(36), ForeignKey("events.id"), nullable=False)
    relationship_type = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("source_event_id", "target_event_id", "relationship_type", name="uq_event_rel"),
    )

    source_event = relationship("Event", foreign_keys=[source_event_id], back_populates="outgoing_relationships")
    target_event = relationship("Event", foreign_keys=[target_event_id], back_populates="incoming_relationships")


# ── Event Evidence ────────────────────────────────────────────────────────────

class EventEvidence(Base):
    """Verbatim text excerpt from a source document supporting an event."""
    __tablename__ = "event_evidence"

    id = Column(String(36), primary_key=True, default=_uuid)
    event_id = Column(String(36), ForeignKey("events.id"), nullable=False)
    document_id = Column(String(36), ForeignKey("documents.id"), nullable=False)

    excerpt = Column(Text, nullable=False)          # Verbatim source text
    page_number = Column(Integer, nullable=True)
    confidence = Column(Float, default=0.5)
    created_at = Column(DateTime, default=_now, nullable=False)

    event = relationship("Event", back_populates="evidence")
    document = relationship("Document", back_populates="evidence")

