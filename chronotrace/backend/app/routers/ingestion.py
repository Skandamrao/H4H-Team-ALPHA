"""Ingestion router — POST /api/ingest"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.ingestion import IngestBatchRequest, IngestBatchResponse
from app.services.ingestion_service import ingest_batch

router = APIRouter(prefix="/api/ingest", tags=["ingestion"])


@router.post("", response_model=IngestBatchResponse)
async def ingest(
    payload: IngestBatchRequest,
    db: AsyncSession = Depends(get_db),
) -> IngestBatchResponse:
    """
    Ingest one or more source records (append-only — Rule D, R10).
    Records are processed in order; the batch_id groups them for traceability.
    """
    return await ingest_batch(db, payload)

