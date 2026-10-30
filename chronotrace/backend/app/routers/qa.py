"""QA router — POST /api/ask"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.queries import QuestionRequest, QuestionAnswer
from app.services.qa_service import answer_question

router = APIRouter(prefix="/api/ask", tags=["qa"])


@router.post("", response_model=QuestionAnswer)
async def ask(
    payload: QuestionRequest,
    db: AsyncSession = Depends(get_db),
) -> QuestionAnswer:
    """
    Answer a historical question about feature evolution.

    The system:
      1. Retrieves relevant events deterministically.
      2. Passes evidence to the LLM for answer synthesis.
      3. Validates all cited sources against the database.
      4. Returns status: SUPPORTED / PARTIALLY_SUPPORTED / CONFLICTED / INSUFFICIENT_EVIDENCE.
    """
    return await answer_question(
        db=db,
        project_id=payload.project_id,
        question=payload.question,
        as_of_event_date=payload.as_of_event_date,
        as_of_ingestion_date=payload.as_of_ingestion_date,
    )

