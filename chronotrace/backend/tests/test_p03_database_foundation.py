"""
P03 Database & Foundation Test Suite
Validates all 10 mandatory acceptance criteria specified in Stage P03:
 1. Project insertion
 2. Batch insertion
 3. Source insertion
 4. Event insertion
 5. Feature-to-event relationships
 6. Source evidence relationships
 7. Foreign key enforcement (integrity check)
 8. Duplicate source processing (provenance preservation)
 9. Transaction rollback on invalid data
 10. Historical records remaining intact after subsequent writes (append-only)
"""
from __future__ import annotations

import pytest
import uuid
from datetime import date, datetime, timezone
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database import AsyncSessionLocal, init_db
from app.models.db_models import (
    Project, IngestionBatch, SourceRecord, Feature, FeatureAlias,
    TemporalEvent, EventEvidence, FeatureRelationship
)
from app.repositories import ProjectRepository, EventRepository, FeatureRepository

def _now():
    return datetime.now(timezone.utc)

@pytest.fixture(autouse=True)
async def ensure_db():
    await init_db()

# ---------------------------------------------------------------------------
# Test 1: Project insertion
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_01_project_insertion():
    async with AsyncSessionLocal() as db:
        repo = ProjectRepository(db)
        pid = f"test-proj-{uuid.uuid4().hex[:6]}"
        proj = await repo.create_project(pid, "Alpha Test Project", "Description of test project")
        await db.commit()

        fetched = await repo.get_by_id(pid)
        assert fetched is not None
        assert fetched.id == pid
        assert fetched.name == "Alpha Test Project"

# ---------------------------------------------------------------------------
# Test 2: Batch insertion
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_02_batch_insertion():
    async with AsyncSessionLocal() as db:
        p_repo = ProjectRepository(db)
        pid = f"test-proj-{uuid.uuid4().hex[:6]}"
        await p_repo.create_project(pid, "Batch Test Project")
        
        batch_id = f"batch-{uuid.uuid4().hex[:6]}"
        batch = await p_repo.create_batch(batch_id, pid, records_count=5, notes="First batch")
        await db.commit()

        res = await db.execute(select(IngestionBatch).where(IngestionBatch.id == batch_id))
        fetched = res.scalars().first()
        assert fetched is not None
        assert fetched.project_id == pid
        assert fetched.records_count == 5
        assert fetched.status == "pending"

# ---------------------------------------------------------------------------
# Test 3: Source insertion
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_03_source_insertion():
    async with AsyncSessionLocal() as db:
        pid = f"test-proj-{uuid.uuid4().hex[:6]}"
        db.add(Project(id=pid, name="Source Project"))
        await db.flush()

        src_id = str(uuid.uuid4())
        src = SourceRecord(
            id=src_id,
            project_id=pid,
            record_type="meeting_notes",
            title="Sprint 1 Kickoff",
            source_date=date(2024, 1, 15),
            source_date_raw="January 15, 2024",
            content="Kickoff notes content",
            author="Priya",
        )
        db.add(src)
        await db.commit()

        res = await db.execute(select(SourceRecord).where(SourceRecord.id == src_id))
        fetched = res.scalars().first()
        assert fetched is not None
        assert fetched.record_type == "meeting_notes"
        assert fetched.source_date == date(2024, 1, 15)

# ---------------------------------------------------------------------------
# Test 4: Event insertion
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_04_event_insertion():
    async with AsyncSessionLocal() as db:
        pid = f"test-proj-{uuid.uuid4().hex[:6]}"
        db.add(Project(id=pid, name="Event Project"))
        src = SourceRecord(id=str(uuid.uuid4()), project_id=pid, record_type="changelog", content="Shipped v1")
        db.add(src)
        await db.flush()

        ev_repo = EventRepository(db)
        ev = await ev_repo.insert_event(
            project_id=pid,
            source_id=src.id,
            event_type="IMPLEMENTED",
            description="Feature A was shipped to prod",
            evidence_excerpt="Shipped v1",
            event_date=date(2024, 2, 1),
            event_date_precision="exact",
            event_date_basis="explicit",
            actor="Ravi",
        )
        await db.commit()

        fetched = await ev_repo.get_by_id(ev.id)
        assert fetched is not None
        assert fetched.event_type == "IMPLEMENTED"
        assert fetched.event_date == date(2024, 2, 1)
        assert fetched.actor == "Ravi"

# ---------------------------------------------------------------------------
# Test 5: Feature-to-event relationships
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_05_feature_to_event_relationships():
    async with AsyncSessionLocal() as db:
        pid = f"test-proj-{uuid.uuid4().hex[:6]}"
        db.add(Project(id=pid, name="Rel Project"))
        src = SourceRecord(id=str(uuid.uuid4()), project_id=pid, record_type="design_spec", content="Spec notes")
        db.add(src)
        
        f_repo = FeatureRepository(db)
        feat = await f_repo.create_feature(pid, "Core Billing")
        
        ev_repo = EventRepository(db)
        ev1 = await ev_repo.insert_event(
            project_id=pid,
            source_id=src.id,
            feature_id=feat.id,
            event_type="PROPOSED",
            description="Proposed Billing",
            evidence_excerpt="Spec notes",
        )
        ev2 = await ev_repo.insert_event(
            project_id=pid,
            source_id=src.id,
            feature_id=feat.id,
            event_type="APPROVED",
            description="Approved Billing",
            evidence_excerpt="Spec notes",
        )
        await db.commit()

        events_for_feat = await ev_repo.list_by_feature(pid, feat.id)
        assert len(events_for_feat) == 2
        types = {e.event_type for e in events_for_feat}
        assert types == {"PROPOSED", "APPROVED"}

# ---------------------------------------------------------------------------
# Test 6: Source evidence relationships
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_06_source_evidence_relationships():
    async with AsyncSessionLocal() as db:
        pid = f"test-proj-{uuid.uuid4().hex[:6]}"
        db.add(Project(id=pid, name="Evidence Project"))
        src = SourceRecord(id=str(uuid.uuid4()), project_id=pid, record_type="decision_log", content="ADR 001 text")
        db.add(src)
        await db.flush()

        ev_repo = EventRepository(db)
        ev = await ev_repo.insert_event(
            project_id=pid,
            source_id=src.id,
            event_type="REJECTED",
            description="Rejected XML support",
            evidence_excerpt="ADR 001 text",
        )
        await db.commit()

        # Query evidence records linked to event and source
        res = await db.execute(select(EventEvidence).where(EventEvidence.event_id == ev.id))
        ev_records = res.scalars().all()
        assert len(ev_records) >= 1
        assert ev_records[0].source_id == src.id
        assert ev_records[0].exact_quote == "ADR 001 text"

# ---------------------------------------------------------------------------
# Test 7: Foreign key enforcement
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_07_foreign_key_enforcement():
    async with AsyncSessionLocal() as db:
        # Try inserting a source pointing to a non-existent project_id
        bogus_source = SourceRecord(
            id=str(uuid.uuid4()),
            project_id="non-existent-project-xyz",
            record_type="meeting_notes",
            content="Some text",
        )
        db.add(bogus_source)
        with pytest.raises(IntegrityError):
            await db.flush()
        await db.rollback()

# ---------------------------------------------------------------------------
# Test 8: Duplicate source processing (preserves distinct provenance)
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_08_duplicate_source_processing():
    async with AsyncSessionLocal() as db:
        pid = f"test-proj-{uuid.uuid4().hex[:6]}"
        db.add(Project(id=pid, name="Provenance Project"))
        await db.flush()

        identical_content = "This exact sentence appears in two different meeting notes."
        
        # Source 1 in Jan
        s1 = SourceRecord(
            id=str(uuid.uuid4()),
            project_id=pid,
            record_type="meeting_notes",
            source_date=date(2024, 1, 10),
            content=identical_content,
        )
        # Source 2 in Feb (e.g. repeated in recap)
        s2 = SourceRecord(
            id=str(uuid.uuid4()),
            project_id=pid,
            record_type="meeting_notes",
            source_date=date(2024, 2, 10),
            content=identical_content,
        )
        db.add_all([s1, s2])
        await db.commit()

        # Both records must coexist without loss of provenance
        res = await db.execute(select(SourceRecord).where(SourceRecord.project_id == pid))
        sources = res.scalars().all()
        assert len(sources) == 2
        dates = {s.source_date for s in sources}
        assert dates == {date(2024, 1, 10), date(2024, 2, 10)}

# ---------------------------------------------------------------------------
# Test 9: Transaction rollback on invalid data
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_09_transaction_rollback_on_invalid_data():
    async with AsyncSessionLocal() as db:
        pid = f"test-proj-{uuid.uuid4().hex[:6]}"
        db.add(Project(id=pid, name="Rollback Project"))
        await db.flush()

        # Add valid source
        valid_src = SourceRecord(id=str(uuid.uuid4()), project_id=pid, record_type="ticket", content="Ticket 1")
        db.add(valid_src)
        await db.flush()

        # Add an invalid event (missing mandatory source_id reference or invalid FK)
        invalid_event = TemporalEvent(
            id=str(uuid.uuid4()),
            project_id=pid,
            source_id="non-existent-source-id",
            event_type="PROPOSED",
            description="Invalid event",
            evidence_excerpt="None",
            event_date_precision="exact",
            event_date_basis="explicit",
        )
        db.add(invalid_event)

        with pytest.raises(IntegrityError):
            await db.flush()

        # Rollback cleanly
        await db.rollback()

        # Verify that rollback prevented partial commits
        res = await db.execute(select(SourceRecord).where(SourceRecord.id == valid_src.id))
        assert res.scalars().first() is None

# ---------------------------------------------------------------------------
# Test 10: Historical records remaining intact after subsequent writes (Rule D)
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_10_historical_records_remain_intact_after_subsequent_writes():
    async with AsyncSessionLocal() as db:
        pid = f"test-proj-{uuid.uuid4().hex[:6]}"
        db.add(Project(id=pid, name="Append Only Project"))
        src1 = SourceRecord(id=str(uuid.uuid4()), project_id=pid, record_type="meeting_notes", content="Original proposal")
        db.add(src1)
        await db.flush()

        ev_repo = EventRepository(db)
        # Initial event at T0
        ev1 = await ev_repo.insert_event(
            project_id=pid,
            source_id=src1.id,
            event_type="PROPOSED",
            description="Search Module v1 proposed",
            evidence_excerpt="Original proposal",
            event_date=date(2024, 1, 1),
        )
        await db.commit()

        initial_event_id = ev1.id
        initial_description = ev1.description

        # Subsequent write at T1 (correction/revision rather than mutation)
        async with AsyncSessionLocal() as db2:
            src2 = SourceRecord(id=str(uuid.uuid4()), project_id=pid, record_type="changelog", content="Updated info")
            db2.add(src2)
            await db2.flush()

            ev_repo2 = EventRepository(db2)
            ev2 = await ev_repo2.insert_event(
                project_id=pid,
                source_id=src2.id,
                event_type="MODIFIED",
                description="Search Module v1 updated with Elasticsearch",
                evidence_excerpt="Updated info",
                event_date=date(2024, 2, 1),
                supersedes_event_id=initial_event_id,
            )
            await db2.commit()

        # Verify historical event 1 was NEVER mutated or deleted (Rule D)
        async with AsyncSessionLocal() as db3:
            res = await db3.execute(select(TemporalEvent).where(TemporalEvent.id == initial_event_id))
            retrieved_ev1 = res.scalars().first()
            assert retrieved_ev1 is not None
            assert retrieved_ev1.description == initial_description
            assert retrieved_ev1.event_type == "PROPOSED"
            assert retrieved_ev1.event_date == date(2024, 1, 1)

            # Both records exist in append-only store
            res_all = await db3.execute(select(TemporalEvent).where(TemporalEvent.project_id == pid))
            all_events = res_all.scalars().all()
            assert len(all_events) == 2

