"""
QA Router — /api/qa/ask and /api/ask
Verifiable historical question answering.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.queries import QuestionRequest, QuestionAnswer
from app.services.qa_service import QuestionAnsweringService

router = APIRouter(tags=["qa"])


@router.post("/qa/ask", response_model=QuestionAnswer)
@router.post("/ask", response_model=QuestionAnswer)
async def ask_question(
    payload: QuestionRequest,
    db: AsyncSession = Depends(get_db),
) -> QuestionAnswer:
    """
    Answer a historical question about feature evolution.

    Execution Pipeline (11 steps):
      1. Receive question.
      2. Identify feature names / references.
      3. Detect relevant date constraints.
      4. Retrieve candidate events with deterministic DB filtering.
      5. Apply temporal filters (event cutoff and/or ingestion cutoff).
      6. Resolve relevant decisions and relationships (SUPERSEDES, EXPLAINS_CHANGE).
      7. Gather source evidence and quotes.
      8. Construct grounded evidence context.
      9. Generate concise answer addressing specific question type:
         - What was implemented by this date?
         - Which recorded decision explains this change?
         - When was a feature introduced?
         - Why was a feature renamed?
         - What alternative was rejected?
         - What was removed?
         - What was the feature's state at a specific date?
      10. Validate citations against database (Rule H).
      11. Return status: SUPPORTED / PARTIALLY_SUPPORTED / CONFLICTED / INSUFFICIENT_EVIDENCE.
    """
    return await QuestionAnsweringService.answer_question(
        db=db,
        project_id=payload.project_id,
        question=payload.question,
        as_of_event_date=payload.as_of_event_date,
        as_of_ingestion_date=payload.as_of_ingestion_date,
    )
