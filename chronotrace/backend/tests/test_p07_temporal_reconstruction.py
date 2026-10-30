"""
P07 Temporal Knowledge Graph and State Reconstruction Test Suite
Validates all acceptance criteria specified in Stage P07:
  1. Chronological ordering (deterministic sorting)
  2. Same-day ordering ambiguity (order_uncertain flag)
  3. Unknown event dates preserved (no fabrication)
  4. Historical state reconstruction as of event date cutoff
  5. Bitemporal ingestion date cutoff (knowledge cutoff)
  6. Rule A: Approval != Implementation in state reconstruction
  7. Rule D: Removal preserves prior implementation history (was_implemented)
  8. Reintroduction accounts for earlier removal without destroying history
  9. Superseded decisions discounted up to cutoff date
  10. Rule F: Normal lifecycle progression is NEVER a conflict
  11. Genuine contradiction detection preserves both source claims
  12. GraphService: Decision to Implementation query
  13. GraphService: Full Temporal Knowledge Graph generation
"""
from __future__ import annotations

import pytest
import uuid
from datetime import date, datetime, timezone, timedelta

from app.database import AsyncSessionLocal, init_db, engine, Base
from app.models.db_models import (
    Project, IngestionBatch, SourceRecord, Feature, FeatureAlias,
    TemporalEvent, EventEvidence, FeatureRelationship, EventRelationship, ConflictRecord
)
from app.services.temporal_engine import TemporalEngine
from app.services.historical_state import HistoricalStateService
from app.services.graph_service import GraphService
from app.services.event_relation_processor import EventRelationProcessor
from app.services.conflict_detector import detect_conflicts_for_feature


def _now():
    return datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
async def setup_clean_db():
    async with engine.begin() as conn:
        from app.models import db_models  # noqa: F401
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


# ---------------------------------------------------------------------------
# Test 1: Chronological Ordering
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_01_chronological_ordering():
    async with AsyncSessionLocal() as db:
        pid = f"proj-ord-{uuid.uuid4().hex[:6]}"
        proj = Project(id=pid, name="Ordering Test")
        db.add(proj)

        feat = Feature(id=f"feat-{uuid.uuid4().hex[:6]}", project_id=pid, canonical_name="Order Feature")
        db.add(feat)

        src = SourceRecord(
            id=f"src-{uuid.uuid4().hex[:6]}", project_id=pid, record_type="spec",
            content="Content", content_fingerprint="fp1"
        )
        db.add(src)
        await db.flush()

        # Add events in reverse chronological order
        d3 = date(2024, 3, 1)
        d2 = date(2024, 2, 1)
        d1 = date(2024, 1, 1)

        e3 = TemporalEvent(
            id=f"ev-3-{uuid.uuid4().hex[:6]}", project_id=pid, feature_id=feat.id,
            event_type="IMPLEMENTED", description="Shipped", event_date=d3,
            source_id=src.id, evidence_excerpt="Shipped"
        )
        e1 = TemporalEvent(
            id=f"ev-1-{uuid.uuid4().hex[:6]}", project_id=pid, feature_id=feat.id,
            event_type="PROPOSED", description="Proposed", event_date=d1,
            source_id=src.id, evidence_excerpt="Proposed"
        )
        e2 = TemporalEvent(
            id=f"ev-2-{uuid.uuid4().hex[:6]}", project_id=pid, feature_id=feat.id,
            event_type="APPROVED", description="Approved", event_date=d2,
            source_id=src.id, evidence_excerpt="Approved"
        )
        db.add_all([e3, e1, e2])
        await db.commit()

        tl = await TemporalEngine.build_feature_timeline(db, feat.id)
        assert tl is not None
        assert len(tl.events) == 3
        # Strict chronological order: d1, d2, d3
        assert tl.events[0].event.event_date == d1
        assert tl.events[1].event.event_date == d2
        assert tl.events[2].event.event_date == d3


# ---------------------------------------------------------------------------
# Test 2: Same-Day Ordering Ambiguity (Requirement C)
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_02_same_day_ordering_ambiguity():
    async with AsyncSessionLocal() as db:
        pid = f"proj-amb-{uuid.uuid4().hex[:6]}"
        db.add(Project(id=pid, name="Ambiguity Test"))
        feat = Feature(id=f"feat-{uuid.uuid4().hex[:6]}", project_id=pid, canonical_name="Ambiguity Feature")
        db.add(feat)
        src = SourceRecord(id=f"src-{uuid.uuid4().hex[:6]}", project_id=pid, record_type="notes", content="c", content_fingerprint="fp2")
        db.add(src)
        await db.flush()

        same_day = date(2024, 4, 10)
        e1 = TemporalEvent(
            id=f"ev-s1-{uuid.uuid4().hex[:6]}", project_id=pid, feature_id=feat.id,
            event_type="MODIFIED", description="Mod 1", event_date=same_day,
            source_id=src.id, evidence_excerpt="Mod 1"
        )
        e2 = TemporalEvent(
            id=f"ev-s2-{uuid.uuid4().hex[:6]}", project_id=pid, feature_id=feat.id,
            event_type="MODIFIED", description="Mod 2", event_date=same_day,
            source_id=src.id, evidence_excerpt="Mod 2"
        )
        db.add_all([e1, e2])
        await db.commit()

        tl = await TemporalEngine.build_feature_timeline(db, feat.id)
        assert tl is not None
        # Requirement C: Ordering must be flagged as uncertain
        assert tl.events[0].order_uncertain is True
        assert tl.events[1].order_uncertain is True


# ---------------------------------------------------------------------------
# Test 3: Unknown Event Dates Preserved (Rule C & Rule G)
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_03_unknown_event_dates_preserved():
    async with AsyncSessionLocal() as db:
        pid = f"proj-unk-{uuid.uuid4().hex[:6]}"
        db.add(Project(id=pid, name="Unknown Date Test"))
        feat = Feature(id=f"feat-{uuid.uuid4().hex[:6]}", project_id=pid, canonical_name="Undated Feature")
        db.add(feat)
        src = SourceRecord(id=f"src-{uuid.uuid4().hex[:6]}", project_id=pid, record_type="notes", content="c", content_fingerprint="fp3")
        db.add(src)
        await db.flush()

        # Undated event
        ev = TemporalEvent(
            id=f"ev-u-{uuid.uuid4().hex[:6]}", project_id=pid, feature_id=feat.id,
            event_type="PROPOSED", description="Undated proposal", event_date=None,
            event_date_precision="unknown", source_id=src.id, evidence_excerpt="Undated proposal"
        )
        db.add(ev)
        await db.commit()

        tl = await TemporalEngine.build_feature_timeline(db, feat.id)
        assert tl is not None
        assert tl.events[0].event.event_date is None
        assert tl.events[0].order_uncertain is True
        # Gaps must report uncertain timing
        assert any("uncertain" in g.lower() for g in tl.gaps)


# ---------------------------------------------------------------------------
# Test 4: Historical State as of Event Date Cutoff
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_04_historical_state_as_of_event_date_cutoff():
    async with AsyncSessionLocal() as db:
        pid = f"proj-cut-{uuid.uuid4().hex[:6]}"
        db.add(Project(id=pid, name="Cutoff Test"))
        feat = Feature(id=f"feat-{uuid.uuid4().hex[:6]}", project_id=pid, canonical_name="Cutoff Feature")
        db.add(feat)
        src = SourceRecord(id=f"src-{uuid.uuid4().hex[:6]}", project_id=pid, record_type="spec", content="c", content_fingerprint="fp4")
        db.add(src)
        await db.flush()

        e_prop = TemporalEvent(
            id=f"ev-p-{uuid.uuid4().hex[:6]}", project_id=pid, feature_id=feat.id,
            event_type="PROPOSED", description="Proposed Jan 1", event_date=date(2024, 1, 1),
            source_id=src.id, evidence_excerpt="Proposed Jan 1"
        )
        e_app = TemporalEvent(
            id=f"ev-a-{uuid.uuid4().hex[:6]}", project_id=pid, feature_id=feat.id,
            event_type="APPROVED", description="Approved Feb 1", event_date=date(2024, 2, 1),
            source_id=src.id, evidence_excerpt="Approved Feb 1"
        )
        e_impl = TemporalEvent(
            id=f"ev-i-{uuid.uuid4().hex[:6]}", project_id=pid, feature_id=feat.id,
            event_type="IMPLEMENTED", description="Shipped March 1", event_date=date(2024, 3, 1),
            source_id=src.id, evidence_excerpt="Shipped March 1"
        )
        db.add_all([e_prop, e_app, e_impl])
        await db.commit()

        # State as of Jan 15: Proposed only
        st_jan = await HistoricalStateService.reconstruct_feature_state(db, feat.id, as_of_event_date=date(2024, 1, 15))
        assert st_jan is not None
        assert st_jan.is_proposed is True
        assert st_jan.is_approved is False
        assert st_jan.is_implemented is False

        # State as of Feb 15: Approved, but not implemented
        st_feb = await HistoricalStateService.reconstruct_feature_state(db, feat.id, as_of_event_date=date(2024, 2, 15))
        assert st_feb is not None
        assert st_feb.is_approved is True
        assert st_feb.is_implemented is False

        # State as of March 15: Implemented
        st_mar = await HistoricalStateService.reconstruct_feature_state(db, feat.id, as_of_event_date=date(2024, 3, 15))
        assert st_mar is not None
        assert st_mar.is_implemented is True


# ---------------------------------------------------------------------------
# Test 5: Bitemporal Ingestion Date Cutoff
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_05_bitemporal_ingestion_date_cutoff():
    async with AsyncSessionLocal() as db:
        pid = f"proj-bitemp-{uuid.uuid4().hex[:6]}"
        db.add(Project(id=pid, name="Bitemporal Test"))
        feat = Feature(id=f"feat-{uuid.uuid4().hex[:6]}", project_id=pid, canonical_name="Bitemporal Feature")
        db.add(feat)
        src = SourceRecord(id=f"src-{uuid.uuid4().hex[:6]}", project_id=pid, record_type="spec", content="c", content_fingerprint="fp5")
        db.add(src)
        await db.flush()

        # Event occurred Jan 1, but was only ingested on Oct 1
        ev_retro = TemporalEvent(
            id=f"ev-retro-{uuid.uuid4().hex[:6]}", project_id=pid, feature_id=feat.id,
            event_type="IMPLEMENTED", description="Discovered historical release",
            event_date=date(2024, 1, 1),
            ingestion_timestamp=datetime(2024, 10, 1, 12, 0, tzinfo=timezone.utc),
            source_id=src.id, evidence_excerpt="Discovered historical release"
        )
        db.add(ev_retro)
        await db.commit()

        # Knowledge cutoff of Sept 1 (before ingestion): Event is invisible!
        st_sept = await HistoricalStateService.reconstruct_feature_state(
            db, feat.id, as_of_event_date=date(2024, 5, 1), as_of_ingestion_date=date(2024, 9, 1)
        )
        assert st_sept is not None
        assert st_sept.is_implemented is False

        # Knowledge cutoff of Oct 15 (after ingestion): Event is visible
        st_oct = await HistoricalStateService.reconstruct_feature_state(
            db, feat.id, as_of_event_date=date(2024, 5, 1), as_of_ingestion_date=date(2024, 10, 15)
        )
        assert st_oct is not None
        assert st_oct.is_implemented is True


# ---------------------------------------------------------------------------
# Test 6: Rule A (Approval != Implementation in state reconstruction)
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_06_approval_does_not_equal_implementation():
    async with AsyncSessionLocal() as db:
        pid = f"proj-rulea-{uuid.uuid4().hex[:6]}"
        db.add(Project(id=pid, name="Rule A Test"))
        feat = Feature(id=f"feat-{uuid.uuid4().hex[:6]}", project_id=pid, canonical_name="Rule A Feature")
        db.add(feat)
        src = SourceRecord(id=f"src-{uuid.uuid4().hex[:6]}", project_id=pid, record_type="adr", content="c", content_fingerprint="fp6")
        db.add(src)
        await db.flush()

        ev = TemporalEvent(
            id=f"ev-app-{uuid.uuid4().hex[:6]}", project_id=pid, feature_id=feat.id,
            event_type="APPROVED", description="Decision: Approved", event_date=date(2024, 1, 10),
            source_id=src.id, evidence_excerpt="Decision: Approved"
        )
        db.add(ev)
        await db.commit()

        st = await HistoricalStateService.reconstruct_feature_state(db, feat.id)
        assert st is not None
        assert st.is_approved is True
        assert st.is_implemented is False
        assert st.was_implemented is False


# ---------------------------------------------------------------------------
# Test 7: Rule D (Removal preserves prior implementation history)
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_07_removal_preserves_prior_implementation_history():
    async with AsyncSessionLocal() as db:
        pid = f"proj-rem-{uuid.uuid4().hex[:6]}"
        db.add(Project(id=pid, name="Removal Test"))
        feat = Feature(id=f"feat-{uuid.uuid4().hex[:6]}", project_id=pid, canonical_name="Basic Search")
        db.add(feat)
        src = SourceRecord(id=f"src-{uuid.uuid4().hex[:6]}", project_id=pid, record_type="changelog", content="c", content_fingerprint="fp7")
        db.add(src)
        await db.flush()

        e_impl = TemporalEvent(
            id=f"ev-imp-{uuid.uuid4().hex[:6]}", project_id=pid, feature_id=feat.id,
            event_type="IMPLEMENTED", description="Shipped in v1", event_date=date(2024, 1, 1),
            source_id=src.id, evidence_excerpt="Shipped in v1"
        )
        e_rem = TemporalEvent(
            id=f"ev-rem-{uuid.uuid4().hex[:6]}", project_id=pid, feature_id=feat.id,
            event_type="REMOVED", description="Deprecated and removed", event_date=date(2024, 4, 30),
            source_id=src.id, evidence_excerpt="Deprecated and removed"
        )
        db.add_all([e_impl, e_rem])
        await db.commit()

        st = await HistoricalStateService.reconstruct_feature_state(db, feat.id, as_of_event_date=date(2024, 5, 1))
        assert st is not None
        assert st.is_removed is True
        assert st.is_implemented is False  # Currently inactive
        assert st.was_implemented is True   # Historical implementation intact!


# ---------------------------------------------------------------------------
# Test 8: Reintroduction accounts for earlier removal without destroying history
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_08_reintroduction_accounts_for_removal():
    async with AsyncSessionLocal() as db:
        pid = f"proj-reintro-{uuid.uuid4().hex[:6]}"
        db.add(Project(id=pid, name="Reintro Test"))
        feat = Feature(id=f"feat-{uuid.uuid4().hex[:6]}", project_id=pid, canonical_name="Telemetry")
        db.add(feat)
        src = SourceRecord(id=f"src-{uuid.uuid4().hex[:6]}", project_id=pid, record_type="spec", content="c", content_fingerprint="fp8")
        db.add(src)
        await db.flush()

        e_rem = TemporalEvent(
            id=f"ev-r1-{uuid.uuid4().hex[:6]}", project_id=pid, feature_id=feat.id,
            event_type="REMOVED", description="Removed in v1.5", event_date=date(2024, 2, 1),
            source_id=src.id, evidence_excerpt="Removed in v1.5"
        )
        e_reintro = TemporalEvent(
            id=f"ev-r2-{uuid.uuid4().hex[:6]}", project_id=pid, feature_id=feat.id,
            event_type="PROPOSED", description="Proposed reintroduction in v2.0", event_date=date(2024, 6, 1),
            source_id=src.id, evidence_excerpt="Proposed reintroduction in v2.0"
        )
        db.add_all([e_rem, e_reintro])
        await db.commit()

        st = await HistoricalStateService.reconstruct_feature_state(db, feat.id, as_of_event_date=date(2024, 7, 1))
        assert st is not None
        assert st.is_reintroduced is True
        assert st.is_removed is False


# ---------------------------------------------------------------------------
# Test 9: Superseded Decisions Discounted
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_09_superseded_decisions_discounted():
    async with AsyncSessionLocal() as db:
        pid = f"proj-super-{uuid.uuid4().hex[:6]}"
        db.add(Project(id=pid, name="Supersede Test"))
        feat = Feature(id=f"feat-{uuid.uuid4().hex[:6]}", project_id=pid, canonical_name="Apple Sign-In")
        db.add(feat)
        src = SourceRecord(id=f"src-{uuid.uuid4().hex[:6]}", project_id=pid, record_type="adr", content="c", content_fingerprint="fp9")
        db.add(src)
        await db.flush()

        e_app = TemporalEvent(
            id="ev-orig-app", project_id=pid, feature_id=feat.id,
            event_type="APPROVED", description="Tentatively approved", event_date=date(2024, 1, 10),
            source_id=src.id, evidence_excerpt="Tentatively approved"
        )
        e_super = TemporalEvent(
            id="ev-super-rej", project_id=pid, feature_id=feat.id,
            event_type="REJECTED", description="ADR-009 supersedes tentative approval: Rejected",
            event_date=date(2024, 3, 20),
            supersedes_event_id="ev-orig-app",
            source_id=src.id, evidence_excerpt="ADR-009 supersedes tentative approval"
        )
        db.add_all([e_app, e_super])
        await db.commit()

        # Prior to supersession (Jan 15): Approved
        st_pre = await HistoricalStateService.reconstruct_feature_state(db, feat.id, as_of_event_date=date(2024, 1, 15))
        assert st_pre is not None
        assert st_pre.is_approved is True
        assert st_pre.is_rejected is False

        # After supersession (March 25): Replaced by rejection
        st_post = await HistoricalStateService.reconstruct_feature_state(db, feat.id, as_of_event_date=date(2024, 3, 25))
        assert st_post is not None
        assert st_post.is_approved is False
        assert st_post.is_rejected is True


# ---------------------------------------------------------------------------
# Test 10: Rule F (Normal lifecycle progression is NEVER a conflict)
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_10_normal_progression_not_a_conflict():
    async with AsyncSessionLocal() as db:
        pid = f"proj-prog-{uuid.uuid4().hex[:6]}"
        db.add(Project(id=pid, name="Progression Test"))
        feat = Feature(id=f"feat-{uuid.uuid4().hex[:6]}", project_id=pid, canonical_name="CSV Export")
        db.add(feat)
        src = SourceRecord(id=f"src-{uuid.uuid4().hex[:6]}", project_id=pid, record_type="spec", content="c", content_fingerprint="fp10")
        db.add(src)
        await db.flush()

        events = [
            TemporalEvent(
                id=f"ev-p-{uuid.uuid4().hex[:6]}", project_id=pid, feature_id=feat.id,
                event_type="PROPOSED", description="Proposed", event_date=date(2024, 9, 1),
                source_id=src.id, evidence_excerpt="Proposed"
            ),
            TemporalEvent(
                id=f"ev-a-{uuid.uuid4().hex[:6]}", project_id=pid, feature_id=feat.id,
                event_type="APPROVED", description="Approved", event_date=date(2024, 9, 5),
                source_id=src.id, evidence_excerpt="Approved"
            ),
            TemporalEvent(
                id=f"ev-i-{uuid.uuid4().hex[:6]}", project_id=pid, feature_id=feat.id,
                event_type="IMPLEMENTED", description="Shipped", event_date=date(2024, 9, 10),
                source_id=src.id, evidence_excerpt="Shipped"
            ),
            TemporalEvent(
                id=f"ev-m-{uuid.uuid4().hex[:6]}", project_id=pid, feature_id=feat.id,
                event_type="MODIFIED", description="Modified", event_date=date(2024, 9, 15),
                source_id=src.id, evidence_excerpt="Modified"
            ),
        ]
        db.add_all(events)
        await db.commit()

        conflicts = await detect_conflicts_for_feature(db, pid, feat.id)
        # Rule F: Zero conflicts allowed for normal progression
        assert len(conflicts) == 0


# ---------------------------------------------------------------------------
# Test 11: Contradiction Detection Preserves Both Source Claims
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_11_contradiction_detection_preserves_both_claims():
    async with AsyncSessionLocal() as db:
        pid = f"proj-contra-{uuid.uuid4().hex[:6]}"
        db.add(Project(id=pid, name="Contra Test"))
        feat = Feature(id=f"feat-{uuid.uuid4().hex[:6]}", project_id=pid, canonical_name="Incompatible Feature")
        db.add(feat)
        src1 = SourceRecord(id=f"src1-{uuid.uuid4().hex[:6]}", project_id=pid, record_type="spec", content="c1", content_fingerprint="fp11a")
        src2 = SourceRecord(id=f"src2-{uuid.uuid4().hex[:6]}", project_id=pid, record_type="notes", content="c2", content_fingerprint="fp11b")
        db.add_all([src1, src2])
        await db.flush()

        # Incompatible claims on same date without supersession
        e_app = TemporalEvent(
            id=f"ev-c1-{uuid.uuid4().hex[:6]}", project_id=pid, feature_id=feat.id,
            event_type="APPROVED", description="Vendor A approved", event_date=date(2024, 5, 1),
            source_id=src1.id, evidence_excerpt="Vendor A approved"
        )
        e_rej = TemporalEvent(
            id=f"ev-c2-{uuid.uuid4().hex[:6]}", project_id=pid, feature_id=feat.id,
            event_type="REJECTED", description="Vendor A rejected", event_date=date(2024, 5, 2),
            source_id=src2.id, evidence_excerpt="Vendor A rejected"
        )
        db.add_all([e_app, e_rej])
        await db.commit()

        conflicts = await detect_conflicts_for_feature(db, pid, feat.id)
        assert len(conflicts) >= 1
        assert conflicts[0].conflict_type == "APPROVED_AND_REJECTED"
        # Both event records must remain in the DB intact
        ev1 = await db.get(TemporalEvent, e_app.id)
        ev2 = await db.get(TemporalEvent, e_rej.id)
        assert ev1 is not None
        assert ev2 is not None


# ---------------------------------------------------------------------------
# Test 12: GraphService Decision to Implementation Query
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_12_graph_service_decision_to_implementation():
    async with AsyncSessionLocal() as db:
        pid = f"proj-d2i-{uuid.uuid4().hex[:6]}"
        db.add(Project(id=pid, name="D2I Test"))
        feat = Feature(id=f"feat-{uuid.uuid4().hex[:6]}", project_id=pid, canonical_name="Parquet Storage")
        db.add(feat)
        src = SourceRecord(id=f"src-{uuid.uuid4().hex[:6]}", project_id=pid, record_type="adr", content="c", content_fingerprint="fp12")
        db.add(src)
        await db.flush()

        e_app = TemporalEvent(
            id=f"ev-d-{uuid.uuid4().hex[:6]}", project_id=pid, feature_id=feat.id,
            event_type="APPROVED", description="ADR-012: Approved Parquet", event_date=date(2024, 4, 14),
            source_id=src.id, evidence_excerpt="ADR-012: Approved Parquet"
        )
        e_impl = TemporalEvent(
            id=f"ev-i-{uuid.uuid4().hex[:6]}", project_id=pid, feature_id=feat.id,
            event_type="IMPLEMENTED", description="Parquet storage merged", event_date=date(2024, 4, 28),
            source_id=src.id, evidence_excerpt="Parquet storage merged"
        )
        db.add_all([e_app, e_impl])
        await db.commit()

        res = await GraphService.get_decision_to_implementation(db, feat.id)
        links = res["decision_to_implementation_links"]
        assert len(links) == 1
        assert links[0]["decision_event_id"] == e_app.id
        assert links[0]["implementation_event_id"] == e_impl.id
        assert links[0]["latency_days"] == 14


# ---------------------------------------------------------------------------
# Test 13: GraphService Full Knowledge Graph Generation
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_13_graph_service_project_knowledge_graph():
    async with AsyncSessionLocal() as db:
        pid = f"proj-kg-{uuid.uuid4().hex[:6]}"
        db.add(Project(id=pid, name="KG Test"))
        feat = Feature(id=f"feat-{uuid.uuid4().hex[:6]}", project_id=pid, canonical_name="OAuth2")
        db.add(feat)
        src = SourceRecord(id=f"src-{uuid.uuid4().hex[:6]}", project_id=pid, record_type="spec", content="c", content_fingerprint="fp13")
        db.add(src)
        await db.flush()

        e_prop = TemporalEvent(
            id=f"ev-p-{uuid.uuid4().hex[:6]}", project_id=pid, feature_id=feat.id,
            event_type="PROPOSED", description="Proposed OAuth2", event_date=date(2024, 1, 10),
            source_id=src.id, evidence_excerpt="Proposed OAuth2"
        )
        e_app = TemporalEvent(
            id=f"ev-a-{uuid.uuid4().hex[:6]}", project_id=pid, feature_id=feat.id,
            event_type="APPROVED", description="Approved OAuth2", event_date=date(2024, 1, 22),
            source_id=src.id, evidence_excerpt="Approved OAuth2"
        )
        db.add_all([e_prop, e_app])
        await db.commit()

        # Connect with relation processor
        await EventRelationProcessor.process_feature_relations(db, pid, feat.id)

        graph = await GraphService.get_project_graph(db, pid)
        assert graph.project_id == pid
        assert len(graph.nodes) >= 3  # feature node + 2 event nodes
        assert len(graph.edges) >= 2  # PROPOSES and APPROVES edges
        edge_types = {e.relationship_type for e in graph.edges}
        assert "PROPOSES" in edge_types
        assert "APPROVES" in edge_types
