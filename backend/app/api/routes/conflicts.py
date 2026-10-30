"""Conflict detection routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.schemas import ConflictListResponse
from app.services.conflict_detector import detect_conflicts

router = APIRouter()


@router.get("/", response_model=ConflictListResponse)
def list_conflicts(db: Session = Depends(get_db)):
    """Detect and return all conflicting historical records."""
    conflicts = detect_conflicts(db)
    return ConflictListResponse(total=len(conflicts), conflicts=conflicts)
