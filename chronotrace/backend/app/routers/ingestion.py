"""
Ingestion router — Endpoints for batch processing, raw text parsing, and source retrieval.
"""
from __future__ import annotations

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.database import get_db
from app.models.db_models import SourceRecord, IngestionBatch
from app.schemas.ingestion import (
    IngestBatchRequest, IngestBatchResponse, SourceRecordIn, NormalizedSourceRecordOut
)
from app.services.ingestion_service import ingest_batch
from app.services.document_parser import DocumentParser

router = APIRouter(prefix="/ingest", tags=["ingestion"])


class RawTextIngestRequest(BaseModel):
    project_id: str
    text: str
    file_reference: Optional[str] = None
    suggested_title: Optional[str] = None
    batch_id: Optional[str] = None


@router.post("", response_model=IngestBatchResponse)
async def ingest(
    payload: IngestBatchRequest,
    db: AsyncSession = Depends(get_db),
) -> IngestBatchResponse:
    """
    Ingest structured records in initial or incremental batch mode.
    Preserves append-only history (Rule D & R10) and prevents duplicate effects.
    """
    return await ingest_batch(db, payload)


@router.post("/raw-text", response_model=IngestBatchResponse)
async def ingest_raw_text(
    payload: RawTextIngestRequest,
    db: AsyncSession = Depends(get_db),
) -> IngestBatchResponse:
    """
    Ingests unstructured or semi-structured raw text (RFC emails, ADRs, release notes, meeting notes).
    Auto-detects document format, normalizes metadata, and triggers idempotent batch ingestion.
    """
    norm_doc = DocumentParser.parse_unstructured_text(
        text=payload.text,
        project_id=payload.project_id,
        file_ref=payload.file_reference,
        suggested_title=payload.suggested_title,
    )

    record_in = SourceRecordIn(
        project_id=norm_doc.project_id,
        record_type=norm_doc.record_type,  # type: ignore[arg-type]
        title=norm_doc.title,
        source_date=norm_doc.source_date,
        source_date_raw=norm_doc.source_date_raw,
        author=norm_doc.author,
        content=norm_doc.content,
        file_reference=norm_doc.file_reference,
        metadata=norm_doc.metadata_json,
    )

    batch_req = IngestBatchRequest(
        records=[record_in],
        batch_id=payload.batch_id,
        notes=f"Auto-parsed raw document: {norm_doc.record_type}",
    )
    return await ingest_batch(db, batch_req)


@router.get("/sources/{source_id}", response_model=NormalizedSourceRecordOut)
async def get_normalized_source(
    source_id: str,
    db: AsyncSession = Depends(get_db),
) -> NormalizedSourceRecordOut:
    """
    Retrieve a canonical normalized source record by its ID.
    Demonstrates source preservation (Task Deliverable).
    """
    result = await db.execute(select(SourceRecord).where(SourceRecord.id == source_id))
    source = result.scalars().first()
    if not source:
        raise HTTPException(status_code=404, detail="Source record not found")
    return NormalizedSourceRecordOut.model_validate(source)


@router.get("/sources", response_model=List[NormalizedSourceRecordOut])
async def list_normalized_sources(
    project_id: str = Query(...),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
) -> List[NormalizedSourceRecordOut]:
    """
    List all normalized sources for a given project.
    """
    result = await db.execute(
        select(SourceRecord)
        .where(SourceRecord.project_id == project_id)
        .order_by(SourceRecord.ingestion_timestamp.desc())
        .limit(limit)
        .offset(offset)
    )
    return [NormalizedSourceRecordOut.model_validate(s) for s in result.scalars().all()]


@router.get("/batches")
async def list_batches(
    project_id: str = Query(...),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """
    List all ingestion batches for a project.
    """
    result = await db.execute(
        select(IngestionBatch)
        .where(IngestionBatch.project_id == project_id)
        .order_by(IngestionBatch.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    batches = result.scalars().all()
    return [
        {
            "id": b.id,
            "project_id": b.project_id,
            "status": b.status,
            "records_count": b.records_count,
            "events_extracted": b.events_extracted,
            "failed_count": b.failed_count,
            "duplicate_count": b.duplicate_count,
            "created_at": b.created_at,
            "completed_at": b.completed_at,
            "notes": b.notes,
        }
        for b in batches
    ]


@router.get("/batches/{batch_id}")
async def get_batch_status(
    batch_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Track batch ingestion status and execution counts.
    """
    result = await db.execute(select(IngestionBatch).where(IngestionBatch.id == batch_id))
    batch = result.scalars().first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    return {
        "id": batch.id,
        "project_id": batch.project_id,
        "status": batch.status,
        "records_count": batch.records_count,
        "events_extracted": batch.events_extracted,
        "failed_count": batch.failed_count,
        "duplicate_count": batch.duplicate_count,
        "created_at": batch.created_at,
        "completed_at": batch.completed_at,
        "notes": batch.notes,
    }
