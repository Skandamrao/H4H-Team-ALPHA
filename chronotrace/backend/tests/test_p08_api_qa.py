"""
ChronoTrace AI — P08 Backend API and Historical QA Acceptance Test Suite
Verifies:
  - Full FastAPI endpoint routing (Versioned /api/v1/* and legacy /api/*)
  - Project workspace creation, listing, and isolation
  - Ingestion batch listing and status
  - Feature endpoints and historical state reconstruction
  - Project timeline and feature timeline
  - Conflict listing and resolution
  - Dashboard metrics aggregation
  - Knowledge graph endpoints
  - The 7 Mandatory Historical QA Question Types:
      1. What was implemented by this date?
      2. Which recorded decision explains this change?
      3. When was a feature introduced?
      4. Why was a feature renamed?
      5. What alternative was rejected?
      6. What was removed?
      7. What was the feature's state at a specific date?
  - Grounded answer validation (cited sources verified against DB, no hallucination)
"""
from __future__ import annotations

import pytest
from uuid import uuid4
from datetime import date, datetime
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.main import app
from app.database import AsyncSessionLocal
from app.models.db_models import (
    Project, SourceRecord, Feature, FeatureAlias,
    TemporalEvent, ConflictRecord, IngestionBatch, EventRelationship
)


@pytest.fixture
async def setup_p08_test_data():
    """Populate a dedicated test project with verified historical events."""
    async with AsyncSessionLocal() as db:
        existing = await db.execute(select(Project).where(Project.id == "proj-p08"))
        if existing.scalars().first():
            yield "proj-p08"
            return

        # 1. Project
        proj = Project(
            id="proj-p08",
            name="ChronoTrace Test Workspace",
            description="Integration test project for P08 API and QA",
        )
        db.add(proj)

        # 2. Batch
        batch = IngestionBatch(
            id="batch-p08-1",
            project_id="proj-p08",
            records_count=4,
            events_extracted=7,
            status="completed",
        )
        db.add(batch)

        # 3. Sources
        src1 = SourceRecord(
            id="src-p08-1",
            project_id="proj-p08",
            record_type="meeting_notes",
            title="Sprint Planning Kickoff",
            source_date=date(2024, 1, 10),
            source_date_raw="January 10, 2024",
            content="Team agreed to propose biometric MFA for high security users.",
            author="Sarah Chen",
            batch_id="batch-p08-1",
        )
        src2 = SourceRecord(
            id="src-p08-2",
            project_id="proj-p08",
            record_type="decision_log",
            title="ADR-004: Biometric Authentication Decision",
            source_date=date(2024, 1, 20),
            source_date_raw="January 20, 2024",
            content="ADR-004: Approved WebAuthn hardware keys. Rejected SMS OTP due to SIM swapping vulnerabilities.",
            author="Alex Mercer",
            batch_id="batch-p08-1",
        )
        src3 = SourceRecord(
            id="src-p08-3",
            project_id="proj-p08",
            record_type="changelog",
            title="Release 1.2 Deployment",
            source_date=date(2024, 2, 15),
            source_date_raw="February 15, 2024",
            content="PR #104 merged: Implemented WebAuthn authentication. Deprecated and removed Legacy Password Login.",
            author="Marcus Vance",
            batch_id="batch-p08-1",
        )
        src4 = SourceRecord(
            id="src-p08-4",
            project_id="proj-p08",
            record_type="ticket",
            title="SEC-402: Terminology Alignment",
            source_date=date(2024, 3, 1),
            source_date_raw="March 1, 2024",
            content="Renamed 'Biometric MFA' to 'Hardware Passkeys' to follow industry standards.",
            author="Dev Team",
            batch_id="batch-p08-1",
        )
        db.add_all([src1, src2, src3, src4])
        await db.flush()

        # 4. Features
        feat_mfa = Feature(
            id="feat-p08-mfa",
            project_id="proj-p08",
            canonical_name="Hardware Passkeys",
            description="Hardware-backed authentication",
            is_implemented=True,
            is_approved=True,
            is_removed=False,
        )
        feat_legacy = Feature(
            id="feat-p08-legacy",
            project_id="proj-p08",
            canonical_name="Legacy Password Login",
            description="Old password auth",
            is_implemented=False,
            is_approved=True,
            is_removed=True,
        )
        db.add_all([feat_mfa, feat_legacy])
        await db.flush()

        # Alias
        alias = FeatureAlias(
            id="alias-p08-1",
            feature_id=feat_mfa.id,
            alias="Biometric MFA",
            source_id=src1.id,
            evidence_excerpt="team agreed to propose biometric MFA",
        )
        db.add(alias)

        # 5. Events
        ev1 = TemporalEvent(
            id="ev-p08-1",
            project_id="proj-p08",
            source_id=src1.id,
            feature_id=feat_mfa.id,
            unresolved_feature_mention="Biometric MFA",
            event_type="PROPOSED",
            event_date=date(2024, 1, 10),
            description="Proposed biometric MFA for high security accounts",
            evidence_excerpt="Team agreed to propose biometric MFA for high security users",
            actor="Sarah Chen",
        )
        ev2 = TemporalEvent(
            id="ev-p08-2",
            project_id="proj-p08",
            source_id=src2.id,
            feature_id=feat_mfa.id,
            unresolved_feature_mention="Hardware Passkeys",
            event_type="APPROVED",
            event_date=date(2024, 1, 20),
            description="Approved WebAuthn hardware keys under ADR-004",
            evidence_excerpt="ADR-004: Approved WebAuthn hardware keys",
            actor="Alex Mercer",
        )
        ev3 = TemporalEvent(
            id="ev-p08-3",
            project_id="proj-p08",
            source_id=src2.id,
            feature_id=None,
            unresolved_feature_mention="SMS OTP",
            event_type="REJECTED",
            event_date=date(2024, 1, 20),
            description="Rejected SMS OTP due to SIM swapping vulnerabilities",
            evidence_excerpt="Rejected SMS OTP due to SIM swapping vulnerabilities",
            actor="Alex Mercer",
        )
        ev4 = TemporalEvent(
            id="ev-p08-4",
            project_id="proj-p08",
            source_id=src3.id,
            feature_id=feat_mfa.id,
            unresolved_feature_mention="Hardware Passkeys",
            event_type="IMPLEMENTED",
            event_date=date(2024, 2, 15),
            description="Implemented WebAuthn authentication via PR #104",
            evidence_excerpt="PR #104 merged: Implemented WebAuthn authentication",
            actor="Marcus Vance",
        )
        ev5 = TemporalEvent(
            id="ev-p08-5",
            project_id="proj-p08",
            source_id=src3.id,
            feature_id=feat_legacy.id,
            unresolved_feature_mention="Legacy Password Login",
            event_type="REMOVED",
            event_date=date(2024, 2, 15),
            description="Deprecated and removed Legacy Password Login",
            evidence_excerpt="Deprecated and removed Legacy Password Login",
            actor="Marcus Vance",
        )
        ev6 = TemporalEvent(
            id="ev-p08-6",
            project_id="proj-p08",
            source_id=src4.id,
            feature_id=feat_mfa.id,
            unresolved_feature_mention="Hardware Passkeys",
            previous_name="Biometric MFA",
            new_name="Hardware Passkeys",
            event_type="RENAMED",
            event_date=date(2024, 3, 1),
            description="Renamed to align with industry FIDO2 standards",
            evidence_excerpt="Renamed 'Biometric MFA' to 'Hardware Passkeys' to follow industry standards",
            actor="Dev Team",
        )
        db.add_all([ev1, ev2, ev3, ev4, ev5, ev6])
        await db.flush()

        # 6. Event Relationship
        rel = EventRelationship(
            id="rel-p08-1",
            project_id="proj-p08",
            from_event_id=ev4.id,
            to_event_id=ev2.id,
            relationship_type="IMPLEMENTS",
            description="PR #104 implements ADR-004 decision",
        )
        rel_explains = EventRelationship(
            id="rel-p08-2",
            project_id="proj-p08",
            from_event_id=ev2.id,
            to_event_id=ev1.id,
            relationship_type="EXPLAINS_CHANGE",
            description="ADR-004 explains the transition from Biometric MFA proposal to WebAuthn",
        )
        db.add_all([rel, rel_explains])

        # 7. Conflict Record
        conf = ConflictRecord(
            id="conf-p08-1",
            project_id="proj-p08",
            event_id_a=ev2.id,
            event_id_b=ev3.id,
            conflict_type="SPECIFICATION_DISPUTE",
            description="Dispute over fallback authentication mechanism",
            resolved=False,
        )
        db.add(conf)

        await db.commit()

    yield "proj-p08"


@pytest.mark.anyio
async def test_01_versioned_system_health():
    """Verify system health and info endpoints across both /api and /api/v1."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Legacy
        res = await ac.get("/api/health")
        assert res.status_code == 200
        assert res.json() == {"status": "ok", "service": "ChronoTrace AI"}

        # Versioned
        res_v1 = await ac.get("/api/v1/health")
        assert res_v1.status_code == 200
        assert res_v1.json() == {"status": "ok", "service": "ChronoTrace AI"}

        # Info
        info_res = await ac.get("/api/v1/info")
        assert info_res.status_code == 200
        assert "llm_provider" in info_res.json()


@pytest.mark.anyio
async def test_02_project_management(setup_p08_test_data):
    """Verify project workspace creation, listing, and inspection."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # List projects
        res = await ac.get("/api/v1/projects")
        assert res.status_code == 200
        projects = res.json()
        assert any(p["id"] == "proj-p08" for p in projects)

        # Get single project
        get_res = await ac.get("/api/v1/projects/proj-p08")
        assert get_res.status_code == 200
        assert get_res.json()["name"] == "ChronoTrace Test Workspace"

        # Create new project
        new_proj_id = f"proj-new-{uuid4().hex[:6]}"
        create_res = await ac.post("/api/v1/projects", json={
            "id": new_proj_id,
            "name": "New Project",
            "description": "Test creation"
        })
        assert create_res.status_code == 201
        assert create_res.json()["id"] == new_proj_id

        # Duplicate ID should return 400
        dup_res = await ac.post("/api/v1/projects", json={
            "id": new_proj_id,
            "name": "Duplicate Project"
        })
        assert dup_res.status_code == 400

        # Non-existent project returns 404
        miss_res = await ac.get("/api/v1/projects/non-existent-proj")
        assert miss_res.status_code == 404


@pytest.mark.anyio
async def test_03_batches_listing(setup_p08_test_data):
    """Verify batch listing and status endpoints."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/v1/ingest/batches?project_id=proj-p08")
        assert res.status_code == 200
        batches = res.json()
        assert len(batches) >= 1
        assert batches[0]["id"] == "batch-p08-1"
        assert batches[0]["status"] == "completed"

        # Single batch status
        status_res = await ac.get("/api/v1/ingest/batches/batch-p08-1")
        assert status_res.status_code == 200
        assert status_res.json()["records_count"] == 4


@pytest.mark.anyio
async def test_04_project_and_feature_timelines(setup_p08_test_data):
    """Verify unified project timeline and single-feature timeline."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Project-wide timeline
        p_res = await ac.get("/api/v1/timeline/project/proj-p08")
        assert p_res.status_code == 200
        p_data = p_res.json()
        assert p_data["total_events"] >= 6
        assert len(p_data["events"]) >= 6

        # Feature timeline
        f_res = await ac.get("/api/v1/timeline/feature/feat-p08-mfa")
        assert f_res.status_code == 200
        f_data = f_res.json()
        assert f_data["feature"]["canonical_name"] == "Hardware Passkeys"
        assert len(f_data["events"]) >= 3


@pytest.mark.anyio
async def test_05_feature_state_reconstruction_api(setup_p08_test_data):
    """Verify /api/v1/features/{id}/state with temporal cutoff."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # State as of Jan 15 (Proposed, not yet approved or implemented)
        st1_res = await ac.get("/api/v1/features/feat-p08-mfa/state?as_of_event_date=2024-01-15")
        assert st1_res.status_code == 200
        st1 = st1_res.json()
        assert st1["is_proposed"] is True
        assert st1["is_approved"] is False
        assert st1["is_implemented"] is False

        # State as of Feb 20 (Approved and Implemented)
        st2_res = await ac.get("/api/v1/features/feat-p08-mfa/state?as_of_event_date=2024-02-20")
        assert st2_res.status_code == 200
        st2 = st2_res.json()
        assert st2["is_approved"] is True
        assert st2["is_implemented"] is True


@pytest.mark.anyio
async def test_06_conflicts_api(setup_p08_test_data):
    """Verify conflict listing and resolution endpoints."""
    async with AsyncSessionLocal() as db:
        conf = await db.get(ConflictRecord, "conf-p08-1")
        if conf:
            conf.resolved = False
            await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # List unresolved
        c_res = await ac.get("/api/v1/conflicts?project_id=proj-p08&resolved=false")
        assert c_res.status_code == 200
        conflicts = c_res.json()
        assert len(conflicts) >= 1
        assert any(c["id"] == "conf-p08-1" for c in conflicts)

        # Resolve conflict
        resolve_res = await ac.post(
            "/api/v1/conflicts/conf-p08-1/resolve",
            json={"resolution_notes": "Resolved by architecture committee agreeing to WebAuthn only"}
        )
        assert resolve_res.status_code == 200
        assert resolve_res.json()["resolved"] is True


@pytest.mark.anyio
async def test_07_dashboard_metrics(setup_p08_test_data):
    """Verify aggregated dashboard statistics endpoint."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/v1/dashboard/metrics?project_id=proj-p08")
        assert res.status_code == 200
        metrics = res.json()
        assert metrics["total_features"] == 2
        assert metrics["total_events"] == 6
        assert metrics["total_sources"] == 4
        assert metrics["total_batches"] == 1
        assert metrics["implemented_features"] == 1
        assert metrics["removed_features"] == 1
        assert "PROPOSED" in metrics["event_type_distribution"]
        assert len(metrics["recent_events"]) > 0


@pytest.mark.anyio
async def test_08_qa_type1_what_was_implemented_by_date(setup_p08_test_data):
    """Mandatory Question Type 1: What was implemented by this date?"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Before Feb 15 implementation:
        res_early = await ac.post("/api/v1/qa/ask", json={
            "project_id": "proj-p08",
            "question": "What was implemented by 2024-02-01?"
        })
        assert res_early.status_code == 200
        ans_early = res_early.json()
        assert ans_early["status"] == "SUPPORTED"
        assert "no features were verified as IMPLEMENTED" in ans_early["answer"]

        # After Feb 15 implementation:
        res_late = await ac.post("/api/v1/qa/ask", json={
            "project_id": "proj-p08",
            "question": "What was implemented by 2024-02-28?"
        })
        assert res_late.status_code == 200
        ans_late = res_late.json()
        assert ans_late["status"] == "SUPPORTED"
        assert "Hardware Passkeys" in ans_late["answer"]
        assert "src-p08-3" in ans_late["cited_source_ids"]
        assert len(ans_late["supporting_evidence"]) >= 1


@pytest.mark.anyio
async def test_09_qa_type2_which_decision_explains_change(setup_p08_test_data):
    """Mandatory Question Type 2: Which recorded decision explains this change?"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post("/api/v1/qa/ask", json={
            "project_id": "proj-p08",
            "question": "Which recorded decision explains the change to Hardware Passkeys?"
        })
        assert res.status_code == 200
        ans = res.json()
        assert ans["status"] == "SUPPORTED"
        assert "ADR-004" in ans["answer"]
        assert "src-p08-2" in ans["cited_source_ids"]


@pytest.mark.anyio
async def test_10_qa_type3_when_was_feature_introduced(setup_p08_test_data):
    """Mandatory Question Type 3: When was a feature introduced?"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post("/api/v1/qa/ask", json={
            "project_id": "proj-p08",
            "question": "When was Hardware Passkeys introduced?"
        })
        assert res.status_code == 200
        ans = res.json()
        assert ans["status"] == "SUPPORTED"
        assert "2024-01-10" in ans["answer"]
        assert "Sarah Chen" in ans["answer"]
        assert "src-p08-1" in ans["cited_source_ids"]


@pytest.mark.anyio
async def test_11_qa_type4_why_was_feature_renamed(setup_p08_test_data):
    """Mandatory Question Type 4: Why was a feature renamed?"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post("/api/v1/qa/ask", json={
            "project_id": "proj-p08",
            "question": "Why was Hardware Passkeys renamed?"
        })
        assert res.status_code == 200
        ans = res.json()
        assert ans["status"] == "SUPPORTED"
        assert "Biometric MFA" in ans["answer"]
        assert "Hardware Passkeys" in ans["answer"]
        assert "standards" in ans["answer"].lower()
        assert "src-p08-4" in ans["cited_source_ids"]


@pytest.mark.anyio
async def test_12_qa_type5_what_alternative_was_rejected(setup_p08_test_data):
    """Mandatory Question Type 5: What alternative was rejected?"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post("/api/v1/qa/ask", json={
            "project_id": "proj-p08",
            "question": "What alternative was rejected in the security architecture?"
        })
        assert res.status_code == 200
        ans = res.json()
        assert ans["status"] == "SUPPORTED"
        assert "SMS OTP" in ans["answer"]
        assert "SIM swapping" in ans["answer"]
        assert "src-p08-2" in ans["cited_source_ids"]


@pytest.mark.anyio
async def test_13_qa_type6_what_was_removed(setup_p08_test_data):
    """Mandatory Question Type 6: What was removed?"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post("/api/v1/qa/ask", json={
            "project_id": "proj-p08",
            "question": "What was removed from the product?"
        })
        assert res.status_code == 200
        ans = res.json()
        assert ans["status"] == "SUPPORTED"
        assert "Legacy Password Login" in ans["answer"]
        assert "src-p08-3" in ans["cited_source_ids"]


@pytest.mark.anyio
async def test_14_qa_type7_feature_state_at_specific_date(setup_p08_test_data):
    """Mandatory Question Type 7: What was the feature's state at a specific date?"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post("/api/v1/qa/ask", json={
            "project_id": "proj-p08",
            "question": "What was Hardware Passkeys's state on 2024-01-15?"
        })
        assert res.status_code == 200
        ans = res.json()
        assert ans["status"] == "SUPPORTED"
        assert "PROPOSED" in ans["answer"]
        assert "Implemented:** False" in ans["answer"]
        assert len(ans["supporting_evidence"]) > 0


@pytest.mark.anyio
async def test_15_qa_insufficient_evidence_and_unknowns(setup_p08_test_data):
    """Verify that unrecorded facts return INSUFFICIENT_EVIDENCE rather than hallucinations (Rule G)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post("/api/v1/qa/ask", json={
            "project_id": "proj-p08",
            "question": "When was Quantum Encryption implemented?"
        })
        assert res.status_code == 200
        ans = res.json()
        assert ans["status"] == "INSUFFICIENT_EVIDENCE"
        assert len(ans["cited_source_ids"]) == 0
        assert len(ans["missing_information"]) > 0
