"""
ChronoTrace AI — FastAPI Application Entry Point
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.routers import (
    ingestion_router, events_router, features_router,
    timeline_router, qa_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database tables on startup."""
    await init_db()
    yield


app = FastAPI(
    title="ChronoTrace AI",
    description=(
        "Temporal Product Knowledge System — "
        "Reconstructs the historical evolution of software features from dated project records."
    ),
    version="1.0.0",
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

# Routers
app.include_router(ingestion_router)
app.include_router(events_router)
app.include_router(features_router)
app.include_router(timeline_router)
app.include_router(qa_router)


@app.get("/api/health", tags=["system"])
async def health() -> dict:
    return {"status": "ok", "service": "ChronoTrace AI"}


@app.get("/api/info", tags=["system"])
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

