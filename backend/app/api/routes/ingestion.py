"""Ingestion batch management routes."""

from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.database import get_db
from app.models.models import IngestionBatch
from app.schemas.schemas import IngestionBatchResponse

router = APIRouter()


@router.get("/batches", response_model=List[IngestionBatchResponse])
def list_batches(db: Session = Depends(get_db)):
    """List all ingestion batches ordered by most recent first."""
    batches = db.query(IngestionBatch).order_by(IngestionBatch.started_at.desc()).all()
    return [
        IngestionBatchResponse(
            id=b.id,
            label=b.label,
            started_at=b.started_at,
            completed_at=b.completed_at,
            status=b.status,
            total_files=b.total_files,
            processed_files=b.processed_files,
            failed_files=b.failed_files,
            duplicate_files=b.duplicate_files,
            new_events_extracted=b.new_events_extracted,
        )
        for b in batches
    ]


@router.get("/batches/{batch_id}", response_model=IngestionBatchResponse)
def get_batch(batch_id: str, db: Session = Depends(get_db)):
    from fastapi import HTTPException
    batch = db.get(IngestionBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found.")
    return IngestionBatchResponse(
        id=batch.id,
        label=batch.label,
        started_at=batch.started_at,
        completed_at=batch.completed_at,
        status=batch.status,
        total_files=batch.total_files,
        processed_files=batch.processed_files,
        failed_files=batch.failed_files,
        duplicate_files=batch.duplicate_files,
        new_events_extracted=batch.new_events_extracted,
    )
