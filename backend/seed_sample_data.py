"""
Seed script for ChronoGraph AI demo dataset.

Populates the database with realistic synthetic events, features, aliases,
decisions, and conflicts derived from the sample documents.
Useful for immediate demoing without requiring a Gemini API key.

Run:
  python seed_sample_data.py
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.database import Base, engine, SessionLocal
from app.models.models import (
    Document, Feature, FeatureAlias, Module, Event, EventEvidence, IngestionBatch
)
from app.services.graph.knowledge_graph import rebuild_graph
from app.services.conflict_detector import detect_conflicts
from app.services.document_processor import compute_file_hash


def seed():
    print("Initializing database tables...")
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    # Clear existing demo data
    print("Clearing old records...")
    db.query(EventEvidence).delete()
    db.query(Event).delete()
    db.query(FeatureAlias).delete()
    db.query(Feature).delete()
    db.query(Module).delete()
    db.query(Document).delete()
    db.query(IngestionBatch).delete()
    db.commit()

    print("Creating Ingestion Batch 1 (Initial Ingestion - October 2024)...")
    batch1 = IngestionBatch(
        label="Batch 1: Core Auth Documents",
        started_at=datetime(2024, 10, 20, 10, 0),
        completed_at=datetime(2024, 10, 20, 10, 5),
        status="COMPLETED",
        total_files=5,
        processed_files=5,
        failed_files=0,
        duplicate_files=0,
        new_events_extracted=8,
    )
    db.add(batch1)
    db.flush()

    # 1. Documents
    sample_dir = os.path.join(os.path.dirname(__file__), "sample_data")
    
    docs = {}
    doc_specs = [
        ("Meeting_Notes_October_5_2024.txt", "txt", datetime(2024, 10, 5)),
        ("ADR_012_Google_OAuth_Approved_October_8_2024.md", "md", datetime(2024, 10, 8)),
        ("PR_247_Google_OAuth_October_12_2024.md", "md", datetime(2024, 10, 12)),
        ("Meeting_Notes_October_15_2024.txt", "txt", datetime(2024, 10, 15)),
        ("Project_Tickets_October_2024.json", "json", datetime(2024, 10, 18)),
    ]

    for fname, ftype, fdate in doc_specs:
        fpath = os.path.join(sample_dir, fname)
        content = b""
        if os.path.exists(fpath):
            with open(fpath, "rb") as f:
                content = f.read()
        fhash = compute_file_hash(content) if content else f"hash_{fname}"
        
        doc = Document(
            ingestion_batch_id=batch1.id,
            filename=fname,
            original_filename=fname,
            file_type=ftype,
            file_size_bytes=len(content) or 2048,
            file_hash=fhash,
            document_date=fdate,
            document_date_confidence="HIGH",
            processing_status="COMPLETED",
            page_count=1,
            is_duplicate=False,
            extracted_text=content.decode("utf-8", errors="replace"),
        )
        db.add(doc)
        db.flush()
        docs[fname] = doc

    # 2. Modules
    mod_auth = Module(
        name="Authentication Module",
        canonical_name="Identity and Access Module",
        description="Handles user authentication, sessions, and OAuth providers."
    )
    db.add(mod_auth)
    db.flush()

    # 3. Features & Aliases
    feat_google = Feature(
        canonical_name="Google Authentication",
        module_id=mod_auth.id,
        current_status="ACTIVE",
        first_seen_date=datetime(2024, 10, 5),
        last_event_date=datetime(2024, 10, 12),
    )
    db.add(feat_google)
    db.flush()

    # Aliases for Google Authentication
    for alias_name, is_canon in [
        ("Google Authentication", True),
        ("Google Login", False),
        ("Google OAuth Integration", False),
        ("Google Sign-In", False),
    ]:
        db.add(FeatureAlias(
            feature_id=feat_google.id,
            alias=alias_name,
            source_document_id=docs["Meeting_Notes_October_5_2024.txt"].id,
            is_canonical=is_canon,
        ))

    feat_password = Feature(
        canonical_name="Password Authentication",
        module_id=mod_auth.id,
        current_status="ACTIVE",
        first_seen_date=datetime(2024, 10, 5),
        last_event_date=datetime(2024, 10, 17),
    )
    db.add(feat_password)
    db.flush()

    db.add(FeatureAlias(
        feature_id=feat_password.id,
        alias="Password Authentication",
        is_canonical=True,
    ))

    feat_github = Feature(
        canonical_name="GitHub Authentication",
        module_id=mod_auth.id,
        current_status="PROPOSED",
        first_seen_date=datetime(2024, 10, 16),
        last_event_date=datetime(2024, 10, 16),
    )
    db.add(feat_github)
    db.flush()

    db.add(FeatureAlias(
        feature_id=feat_github.id,
        alias="GitHub Authentication",
        is_canonical=True,
    ))

    # 4. Events & Evidence
    # Event 1: Google Login Proposed
    ev1 = Event(
        feature_id=feat_google.id,
        source_document_id=docs["Meeting_Notes_October_5_2024.txt"].id,
        title="Google Login Integration Proposed",
        description="Marcus Rivera proposed introducing Google Login as an alternative authentication method to reduce onboarding friction.",
        event_type="DECISION_PROPOSED",
        decision_status="PROPOSED",
        feature_name_in_source="Google Login",
        module_name="Authentication Module",
        reason="User research shows 72% of target users already have Google accounts; 34% rise in password support tickets.",
        event_date=datetime(2024, 10, 5),
        event_date_confidence="HIGH",
        confidence_score=0.95,
        supporting_text="Marcus Rivera proposed introducing Google Login as an alternative authentication method. Status: PROPOSED — awaiting engineering review.",
    )
    db.add(ev1)
    db.flush()
    db.add(EventEvidence(
        event_id=ev1.id,
        document_id=docs["Meeting_Notes_October_5_2024.txt"].id,
        excerpt="Marcus Rivera proposed introducing Google Login as an alternative authentication method. This would allow users to sign in using their existing Google accounts...",
        confidence=0.95,
    ))

    # Event 2: ADR-012 Google OAuth Approved
    ev2 = Event(
        feature_id=feat_google.id,
        source_document_id=docs["ADR_012_Google_OAuth_Approved_October_8_2024.md"].id,
        title="ADR-012: Google OAuth 2.0 Integration Approved",
        description="Engineering lead Sarah Chen approved the implementation of Google OAuth 2.0 following technical feasibility assessment.",
        event_type="DECISION_APPROVED",
        decision_status="APPROVED",
        feature_name_in_source="Google Authentication",
        module_name="Authentication Module",
        reason="Technical feasibility confirmed; low implementation risk; security team approved OAuth 2.0 compliance.",
        event_date=datetime(2024, 10, 8),
        event_date_confidence="HIGH",
        confidence_score=0.98,
        supporting_text="APPROVED: Google Authentication feature will be implemented using Google Identity Platform / OAuth 2.0.",
    )
    db.add(ev2)
    db.flush()
    db.add(EventEvidence(
        event_id=ev2.id,
        document_id=docs["ADR_012_Google_OAuth_Approved_October_8_2024.md"].id,
        excerpt="The engineering team has approved the implementation of Google OAuth 2.0 integration as a new authentication method for the platform.",
        confidence=0.98,
    ))

    # Event 3: PR-247 Google OAuth Implemented
    ev3 = Event(
        feature_id=feat_google.id,
        source_document_id=docs["PR_247_Google_OAuth_October_12_2024.md"].id,
        title="PR-247: Google OAuth Integration Implemented and Merged",
        description="Priya Patel merged PR-247 introducing GoogleOAuthProvider and callback endpoints. Feature is live in production.",
        event_type="FEATURE_IMPLEMENTED",
        decision_status="IMPLEMENTED",
        feature_name_in_source="Google OAuth Integration",
        module_name="Authentication Module",
        reason="Fulfill approved ADR-012 architecture decision.",
        event_date=datetime(2024, 10, 12),
        event_date_confidence="HIGH",
        confidence_score=0.99,
        supporting_text="Status: IMPLEMENTED — feature is live in production as of October 12, 2024.",
    )
    db.add(ev3)
    db.flush()
    db.add(EventEvidence(
        event_id=ev3.id,
        document_id=docs["PR_247_Google_OAuth_October_12_2024.md"].id,
        excerpt="Added GoogleOAuthProvider class in auth/providers/google_oauth.py... Status: IMPLEMENTED — feature is live in production as of October 12, 2024.",
        confidence=0.99,
    ))

    # Event 4: Module Rename Approved
    ev4 = Event(
        feature_id=feat_google.id,
        source_document_id=docs["Meeting_Notes_October_15_2024.txt"].id,
        title="Authentication Module Renamed to Identity and Access Module",
        description="Team approved renaming the Authentication Module to Identity and Access Module to reflect scope expansion to authorization/RBAC.",
        event_type="FEATURE_RENAMED",
        decision_status="APPROVED",
        feature_name_in_source="Identity and Access Module",
        module_name="Identity and Access Module",
        reason="Reflect planned expansion to cover authorization (RBAC) in addition to authentication.",
        event_date=datetime(2024, 10, 15),
        event_date_confidence="HIGH",
        confidence_score=0.94,
        supporting_text="Decision: APPROVED — the module will be renamed. Effective date: November 1, 2024.",
    )
    db.add(ev4)
    db.flush()

    # Event 5: Conflicting Record - Password Removal Draft Approved vs Formal Rejection
    ev5_a = Event(
        feature_id=feat_password.id,
        source_document_id=docs["Meeting_Notes_October_15_2024.txt"].id,
        title="Immediate Password Auth Removal (Erroneous Approval Draft)",
        description="Earlier informal agenda draft incorrectly listed immediate password removal as APPROVED.",
        event_type="DECISION_APPROVED",
        decision_status="APPROVED",
        feature_name_in_source="Password Authentication",
        module_name="Identity and Access Module",
        event_date=datetime(2024, 10, 18),
        event_date_confidence="MEDIUM",
        confidence_score=0.60,
        has_conflict=True,
        conflict_note="Contradicted by official ticket AUTH-104 rejecting immediate removal.",
        supporting_text="Note: An earlier draft of this meeting agenda incorrectly listed the Password Authentication deprecation as APPROVED.",
    )
    ev5_b = Event(
        feature_id=feat_password.id,
        source_document_id=docs["Meeting_Notes_October_15_2024.txt"].id,
        title="Password Authentication Phased Deprecation Proposed",
        description="Team formally voted that Password Authentication deprecation is PROPOSED pending review by the wider engineering team.",
        event_type="DECISION_PROPOSED",
        decision_status="PROPOSED",
        feature_name_in_source="Password Authentication",
        module_name="Identity and Access Module",
        event_date=datetime(2024, 10, 15),
        event_date_confidence="HIGH",
        confidence_score=0.92,
        has_conflict=False,
        supporting_text="STATUS: PROPOSED — team voted to take this to the wider engineering team for review. No removal decision has been made.",
    )
    db.add_all([ev5_a, ev5_b])
    db.flush()

    # Event 6: Rejected Ticket AUTH-104
    ev6 = Event(
        feature_id=feat_password.id,
        source_document_id=docs["Project_Tickets_October_2024.json"].id,
        title="Ticket AUTH-104: Immediate Removal of Password Auth Rejected",
        description="Proposal for immediate removal was formally rejected by Sarah Chen. Phased deprecation remains active.",
        event_type="DECISION_REJECTED",
        decision_status="REJECTED",
        feature_name_in_source="Password Authentication",
        module_name="Identity and Access Module",
        reason="Immediate removal poses risk to enterprise customers and accessibility.",
        event_date=datetime(2024, 10, 18),
        event_date_confidence="HIGH",
        confidence_score=0.96,
        supporting_text="An informal proposal to remove password authentication immediately was reviewed and rejected.",
    )
    db.add(ev6)

    # Event 7: GitHub Auth Proposed
    ev7 = Event(
        feature_id=feat_github.id,
        source_document_id=docs["Project_Tickets_October_2024.json"].id,
        title="Ticket AUTH-101: GitHub OAuth Proposed",
        description="Priya Patel created ticket AUTH-101 proposing GitHub OAuth as a second sign-in option.",
        event_type="DECISION_PROPOSED",
        decision_status="PROPOSED",
        feature_name_in_source="GitHub Authentication",
        module_name="Identity and Access Module",
        reason="Follow success of Google OAuth, targeting developer users.",
        event_date=datetime(2024, 10, 16),
        event_date_confidence="HIGH",
        confidence_score=0.90,
        supporting_text="AUTH-101: Implement GitHub OAuth as second OAuth provider. Status: PROPOSED. Awaiting product approval.",
    )
    db.add(ev7)

    db.commit()

    print("Rebuilding knowledge graph...")
    rebuild_graph(db)

    print("Running conflict detection...")
    conflicts = detect_conflicts(db)
    print(f"Conflicts detected: {len(conflicts)}")

    print("\n[SUCCESS] Seed completed successfully!")
    print(f"  Documents: {db.query(Document).count()}")
    print(f"  Features:  {db.query(Feature).count()}")
    print(f"  Events:    {db.query(Event).count()}")
    print(f"  Conflicts: {len(conflicts)}")
    db.close()


if __name__ == "__main__":
    seed()
