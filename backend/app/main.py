"""
ChronoGraph AI — FastAPI Application Entry Point.

Initialises the application, registers all routers, configures CORS,
and sets up the database tables on startup.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.logging_config import setup_logging
from app.db.database import engine, Base
from app.api.routes import (
    documents,
    events,
    features,
    graph,
    assistant,
    ingestion,
    timeline,
    conflicts,
)

# ── Logging ─────────────────────────────────────────────────────────────────
setup_logging()
logger = logging.getLogger(__name__)


# ── Lifespan (startup / shutdown) ────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create database tables on startup."""
    logger.info("ChronoGraph AI starting up …")
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables verified / created.")
    yield
    logger.info("ChronoGraph AI shutting down.")


# ── Application factory ───────────────────────────────────────────────────────
def create_application() -> FastAPI:
    application = FastAPI(
        title="ChronoGraph AI",
        description="Temporal Product Knowledge System — AI-powered historical intelligence for software projects.",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    # ── CORS ─────────────────────────────────────────────────────────────────
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routers ───────────────────────────────────────────────────────────────
    application.include_router(documents.router, prefix="/api/documents", tags=["Documents"])
    application.include_router(events.router, prefix="/api/events", tags=["Events"])
    application.include_router(features.router, prefix="/api/features", tags=["Features"])
    application.include_router(graph.router, prefix="/api/graph", tags=["Knowledge Graph"])
    application.include_router(assistant.router, prefix="/api/assistant", tags=["AI Assistant"])
    application.include_router(ingestion.router, prefix="/api/ingestion", tags=["Ingestion"])
    application.include_router(timeline.router, prefix="/api/timeline", tags=["Timeline"])
    application.include_router(conflicts.router, prefix="/api/conflicts", tags=["Conflicts"])

    return application


app = create_application()


@app.get("/api/health", tags=["Health"])
async def health_check():
    """Simple liveness probe."""
    return {"status": "ok", "service": "ChronoGraph AI", "version": "1.0.0"}

