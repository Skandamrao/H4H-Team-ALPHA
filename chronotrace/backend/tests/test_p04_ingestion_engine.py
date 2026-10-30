"""
P04 Document Ingestion Engine Test Suite
Validates all requirements specified in Stage P04:
 - Multi-format document parsing (JSON, RFC email, ADR, changelog, meeting notes)
 - Canonical SourceRecord normalization & date preservation (Rule C)
 - Batch tracking (initial vs incremental modes, status metrics)
 - Idempotent deduplication (duplicate detection, no duplicate extraction effects)
 - Fault tolerance & partial failure resilience (malformed records do not crash batch)
 - Retrieval of normalized source record via API
"""
from __future__ import annotations

import pytest
import json
import uuid
from httpx import AsyncClient, ASGITransport
from datetime import date
from sqlalchemy import select

from app.main import app
from app.database import AsyncSessionLocal, init_db
from app.models.db_models import SourceRecord, TemporalEvent, IngestionBatch
from app.services.document_parser import DocumentParser, compute_fingerprint
from app.schemas.ingestion import IngestBatchRequest, SourceRecordIn

@pytest.fixture(autouse=True)
async def setup_db():
    await init_db()

# ---------------------------------------------------------------------------
# Test 1: JSON Batch Parsing (Organizer dataset Batch 1)
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_01_json_batch_parsing():
    with open("fixtures/batch1_records.json", encoding="utf-8") as f:
        records_raw = json.load(f)

    assert len(records_raw) == 5
    pid = f"proj-b1-{uuid.uuid4().hex[:6]}"
    req = IngestBatchRequest(
        records=[SourceRecordIn(**{**r, "project_id": pid}) for r in records_raw],
        mode="initial",
        batch_id=f"test-b1-{uuid.uuid4().hex[:6]}",
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/ingest", json=req.model_dump(mode="json"))
        assert resp.status_code == 200
        data = resp.json()
        assert data["records_processed"] == 5
        assert data["successful_records"] == 5
        assert data["failed_records"] == 0
        assert data["total_events_extracted"] > 0

# ---------------------------------------------------------------------------
# Test 2: Raw ADR Document Parsing
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_02_adr_document_parsing():
    adr_text = """
ADR-012: Adopt Apache Parquet for Analytical Reports

Status: APPROVED
Date: April 14, 2024
Decision makers: Priya Sharma, Dev Patel

## Context
CSV exports struggle with massive analytical datasets exceeding 100MB.

## Decision
Adopt Parquet as the primary internal storage format for the Comms Engine logs.
"""
    doc = DocumentParser.parse_unstructured_text(adr_text, project_id="proj-alpha")
    assert doc.record_type == "decision_log"
    assert doc.title == "ADR-012: Adopt Apache Parquet for Analytical Reports"
    assert doc.source_date == date(2024, 4, 14)
    assert doc.source_date_raw == "April 14, 2024"
    assert "Priya Sharma" in (doc.author or "")
    assert doc.metadata_json.get("adr_status") == "APPROVED"

# ---------------------------------------------------------------------------
# Test 3: Raw RFC Email Thread Parsing
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_03_email_thread_parsing():
    email_text = """From: Ananya Nair <ananya@example.com>
To: Dev Patel <dev@example.com>
Date: May 12, 2024
Subject: Re: Billing Migration Status

Dev,
Confirmed that legacy stripe webhooks are completely deprecated.
New webhooks are live in production as of yesterday.
"""
    doc = DocumentParser.parse_unstructured_text(email_text, project_id="proj-alpha")
    assert doc.record_type == "email_thread"
    assert "Ananya Nair" in (doc.author or "")
    assert doc.title == "Re: Billing Migration Status"
    assert doc.source_date == date(2024, 5, 12)
    assert doc.source_date_raw == "May 12, 2024"

# ---------------------------------------------------------------------------
# Test 4: Raw Changelog / Release Notes Parsing
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_04_changelog_parsing():
    changelog_text = """## Notification Service v3.0 — Released June 1, 2024
### New Features
- Full SMS multi-channel support live in production.
"""
    doc = DocumentParser.parse_unstructured_text(changelog_text, project_id="proj-alpha")
    assert doc.record_type == "changelog"
    assert "Notification Service v3.0" in (doc.title or "")
    assert doc.source_date == date(2024, 6, 1)

# ---------------------------------------------------------------------------
# Test 5: Raw Meeting Notes Parsing
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_05_meeting_notes_parsing():
    meeting_text = """Sprint Retrospective — Q2 2024
Attendees: Ravi Kumar, Dev Patel, Priya Sharma

Agenda: Review search migration
1. Intelligent Search rollout is 100% complete.
"""
    doc = DocumentParser.parse_unstructured_text(meeting_text, project_id="proj-alpha")
    assert doc.record_type == "meeting_notes"
    assert "Sprint Retrospective" in (doc.title or "")
    assert "Ravi Kumar" in (doc.author or "")
    assert "Dev Patel" in doc.metadata_json.get("attendees", [])

# ---------------------------------------------------------------------------
# Test 6: Missing Date Handling (Rule C Invariant)
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_06_missing_date_handling():
    undated_text = """Draft Architecture Proposal
No date mentioned in this document anywhere.
Proposed adding WebSockets to real-time events.
"""
    doc = DocumentParser.parse_unstructured_text(undated_text, project_id="proj-alpha")
    # Rule C: Unknown date remains None, never defaulted to today()
    assert doc.source_date is None
    assert doc.source_date_raw is None

# ---------------------------------------------------------------------------
# Test 7: Duplicate Upload Idempotency (Task D)
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_07_duplicate_upload_idempotency():
    pid = f"proj-idemp-{uuid.uuid4().hex[:6]}"
    record = SourceRecordIn(
        project_id=pid,
        record_type="design_spec",
        title="WebSockets Architecture Spec",
        source_date=date(2024, 3, 1),
        source_date_raw="March 1, 2024",
        author="Dev Patel",
        content="Detailed technical specification for WebSockets integration.",
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # First Ingestion
        resp1 = await ac.post("/api/ingest", json={"records": [record.model_dump(mode="json")]})
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert data1["successful_records"] == 1
        assert data1["duplicate_records"] == 0
        original_source_id = data1["results"][0]["source_id"]

        # Duplicate Ingestion of the exact same document
        resp2 = await ac.post("/api/ingest", json={"records": [record.model_dump(mode="json")]})
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["successful_records"] == 0
        assert data2["duplicate_records"] == 1
        assert data2["total_events_extracted"] == 0  # No duplicate extraction effects!
        assert data2["results"][0]["status"] == "duplicate"
        assert data2["results"][0]["source_id"] == original_source_id

# ---------------------------------------------------------------------------
# Test 8: Partial Failure Resilience (Task E)
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_08_partial_failure_resilience():
    pid = f"proj-partial-{uuid.uuid4().hex[:6]}"
    
    valid_rec = SourceRecordIn(
        project_id=pid,
        record_type="meeting_notes",
        title="Valid Meeting Record",
        content="Sprint discussion on authentication.",
    )
    # Invalid record with empty content
    invalid_rec = SourceRecordIn(
        project_id=pid,
        record_type="other",
        title="Invalid Record",
        content="   ",  # will fail validation in _ingest_single_record
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/ingest", json={"records": [
            valid_rec.model_dump(mode="json"),
            invalid_rec.model_dump(mode="json"),
        ]})
        assert resp.status_code == 200
        data = resp.json()
        # Batch should not abort; valid record succeeds, invalid record reports failure
        assert data["records_processed"] == 2
        assert data["successful_records"] == 1
        assert data["failed_records"] == 1
        statuses = [r["status"] for r in data["results"]]
        assert "success" in statuses
        assert "failed" in statuses

# ---------------------------------------------------------------------------
# Test 9: Initial vs Incremental Mode Tracking (Task C)
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_09_initial_vs_incremental_mode():
    pid = f"proj-mode-{uuid.uuid4().hex[:6]}"
    r1 = SourceRecordIn(project_id=pid, record_type="ticket", content="Ticket 101 description")
    r2 = SourceRecordIn(project_id=pid, record_type="ticket", content="Ticket 102 description")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Batch 1 in initial mode
        b1_resp = await ac.post("/api/ingest", json={"records": [r1.model_dump(mode="json")], "mode": "initial"})
        assert b1_resp.status_code == 200
        assert b1_resp.json()["mode"] == "initial"
        b1_id = b1_resp.json()["batch_id"]

        # Batch 2 in incremental mode
        b2_resp = await ac.post("/api/ingest", json={"records": [r2.model_dump(mode="json")], "mode": "incremental"})
        assert b2_resp.status_code == 200
        assert b2_resp.json()["mode"] == "incremental"

        # Check Batch Status endpoint
        status_resp = await ac.get(f"/api/ingest/batches/{b1_id}")
        assert status_resp.status_code == 200
        assert status_resp.json()["status"] == "completed"

# ---------------------------------------------------------------------------
# Test 10: Ingest Raw Text & Retrieve Normalized Format (Deliverable Demo)
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_10_ingest_raw_and_retrieve_normalized():
    pid = f"proj-norm-{uuid.uuid4().hex[:6]}"
    raw_meeting_text = """From: Security Team <security@example.com>
To: Priya Sharma <priya@example.com>
Date: March 18, 2024
Subject: Security Audit Sign-off for Intelligent Search

Priya,
The automated penetration tests for Intelligent Search passed successfully.
Elasticsearch indices are properly isolated.
"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. Ingest via raw-text endpoint
        ingest_resp = await ac.post("/api/ingest/raw-text", json={
            "project_id": pid,
            "text": raw_meeting_text,
            "file_reference": "raw_email_01.txt",
        })
        assert ingest_resp.status_code == 200
        res = ingest_resp.json()
        assert res["successful_records"] == 1
        source_id = res["results"][0]["source_id"]

        # 2. Retrieve normalized source record
        source_resp = await ac.get(f"/api/ingest/sources/{source_id}")
        assert source_resp.status_code == 200
        norm = source_resp.json()
        assert norm["id"] == source_id
        assert norm["project_id"] == pid
        assert norm["record_type"] == "email_thread"
        assert norm["title"] == "Security Audit Sign-off for Intelligent Search"
        assert norm["author"] == "Security Team <security@example.com>"
        assert norm["source_date"] == "2024-03-18"
        assert norm["file_reference"] == "raw_email_01.txt"
        assert norm["content_fingerprint"] is not None
