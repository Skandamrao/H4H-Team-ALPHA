"""
End-to-end integration test: Ingestion of fixtures, timeline retrieval, and QA.
Verifies the complete flow without needing a mock or live LLM network connection.
"""
import pytest
import json
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.database import init_db

@pytest.fixture(autouse=True)
async def setup_db():
    await init_db()

@pytest.mark.anyio
async def test_full_ingestion_and_evolution_flow():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. Ingest Batch 1
        with open("fixtures/batch1_records.json", encoding="utf-8") as f:
            b1 = json.load(f)

        resp1 = await ac.post("/api/ingest", json={"records": b1})
        assert resp1.status_code == 200
        res1 = resp1.json()
        assert res1["records_processed"] == 5
        assert res1["total_events_extracted"] > 0
        assert res1["total_features_identified"] > 0

        # 2. Ingest Batch 2 (Incremental update without overwriting — Rule D & R10)
        with open("fixtures/batch2_records.json", encoding="utf-8") as f:
            b2 = json.load(f)

        resp2 = await ac.post("/api/ingest", json={"records": b2})
        assert resp2.status_code == 200
        res2 = resp2.json()
        assert res2["records_processed"] == 3

        # 3. Check Features List
        feat_resp = await ac.get("/api/features?project_id=proj-alpha")
        assert feat_resp.status_code == 200
        features = feat_resp.json()
        assert len(features) >= 3

        # 4. Check Timeline for a Feature
        target_feature = features[0]
        tl_resp = await ac.get(f"/api/timeline/feature/{target_feature['id']}")
        assert tl_resp.status_code == 200
        timeline = tl_resp.json()
        assert "events" in timeline
        assert "feature" in timeline

        # 5. Check QA
        qa_resp = await ac.post("/api/ask", json={
            "project_id": "proj-alpha",
            "question": "What happened to OAuth2 Social Login?"
        })
        assert qa_resp.status_code == 200
        qa_data = qa_resp.json()
        assert qa_data["status"] in ["SUPPORTED", "PARTIALLY_SUPPORTED", "CONFLICTED"]
        assert len(qa_data["cited_source_ids"]) > 0

