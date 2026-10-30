"""
Integration tests for ChronoTrace AI ingestion and querying endpoints.
"""
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.database import init_db

@pytest.fixture(autouse=True)
async def setup_db():
    await init_db()

@pytest.mark.anyio
async def test_health():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "service": "ChronoTrace AI"}

@pytest.mark.anyio
async def test_info():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/info")
        assert resp.status_code == 200
        data = resp.json()
        assert data["service"] == "ChronoTrace AI"
        assert "llm_provider" in data

