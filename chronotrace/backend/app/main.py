"""
ChronoTrace AI — FastAPI Application Entry Point (P08)
Complete, unified REST API with versioned endpoints (/api/v1/* and /api/*).
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.routers import (
    projects_router,
    ingestion_router,
    events_router,
    features_router,
    timeline_router,
    qa_router,
    graph_router,
    conflicts_router,
    dashboard_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database tables on startup."""
    await init_db()
    yield


tags_metadata = [
    {
        "name": "system",
        "description": "System health, service telemetry, and configuration metadata.",
    },
    {
        "name": "projects",
        "description": "Project workspace management and isolation boundaries.",
    },
    {
        "name": "ingestion",
        "description": "Document parsing, normalization, and idempotent batch ingestion (Initial & Incremental).",
    },
    {
        "name": "events",
        "description": "Append-only temporal event inspection and provenance tracing.",
    },
    {
        "name": "features",
        "description": "Canonical feature management, alias tracking, and historical state reconstruction.",
    },
    {
        "name": "timeline",
        "description": "Deterministic chronological ordering, milestone labeling, and project timelines.",
    },
    {
        "name": "qa",
        "description": "Verifiable, evidence-grounded historical question answering with verified citations.",
    },
    {
        "name": "graph",
        "description": "Temporal knowledge graph linking entities, decisions, and evidence.",
    },
    {
        "name": "conflicts",
        "description": "Detection, auditing, and resolution of historical contradictions.",
    },
    {
        "name": "dashboard",
        "description": "Aggregated project health metrics and distribution analytics.",
    },
]

app = FastAPI(
    title="ChronoTrace AI",
    description=(
        "Temporal Product Knowledge System — "
        "Reconstructs the historical evolution of software features from dated project records."
    ),
    version="1.0.0",
    openapi_tags=tags_metadata,
    lifespan=lifespan,
)

# CORS for local frontend dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# API Routers Assembly: Versioned (/api/v1) and Aliased (/api)
# ---------------------------------------------------------------------------

all_sub_routers = [
    projects_router,
    ingestion_router,
    events_router,
    features_router,
    timeline_router,
    qa_router,
    graph_router,
    conflicts_router,
    dashboard_router,
]

# Versioned router (/api/v1)
api_v1_router = APIRouter(prefix="/api/v1")
for r in all_sub_routers:
    api_v1_router.include_router(r)

# Unversioned legacy/standard alias router (/api)
api_router = APIRouter(prefix="/api")
for r in all_sub_routers:
    api_router.include_router(r)

app.include_router(api_v1_router)
app.include_router(api_router)


# ---------------------------------------------------------------------------
# System Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health", tags=["system"])
@app.get("/api/v1/health", tags=["system"])
async def health() -> dict:
    return {"status": "ok", "service": "ChronoTrace AI"}


@app.get("/api/info", tags=["system"])
@app.get("/api/v1/info", tags=["system"])
async def info() -> dict:
    return {
        "service": "ChronoTrace AI",
        "version": "1.0.0",
        "llm_provider": settings.llm_provider,
        "llm_model": (
            settings.gemini_model
            if settings.llm_provider == "gemini"
            else settings.openai_model
        ),
    }
