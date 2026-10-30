"""AI Assistant routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.schemas import AssistantQuery, AssistantAnswer
from app.services.historical_assistant import get_assistant

router = APIRouter()

SUGGESTED_QUESTIONS = [
    "What features were introduced in the project?",
    "Which decisions were approved?",
    "Which proposals were never implemented?",
    "What was the original name of the authentication module?",
    "Which features were deprecated or removed?",
    "What changes happened in the last two weeks?",
    "Are there any conflicting historical records?",
    "What was implemented after the architecture review decision?",
]


@router.post("/ask", response_model=AssistantAnswer)
def ask_assistant(query: AssistantQuery, db: Session = Depends(get_db)):
    """Answer a historical question using the project knowledge base."""
    assistant = get_assistant()
    return assistant.answer(db=db, question=query.question)


@router.get("/suggestions")
def get_suggestions(db: Session = Depends(get_db)):
    """Return suggested historical questions for the UI, dynamically enhanced with real features."""
    from app.models.models import Feature

    dynamic_questions = []
    try:
        top_features = db.query(Feature).order_by(Feature.canonical_name).limit(3).all()
        for feat in top_features:
            dynamic_questions.append(f"Why was {feat.canonical_name} introduced?")
            dynamic_questions.append(f"What is the complete timeline of {feat.canonical_name}?")
    except Exception:
        pass

    combined = dynamic_questions + [
        "Which architecture decisions were approved?",
        "Which proposals were never implemented?",
        "Are there any conflicting historical records?",
        "What changes happened across the project?",
    ]
    # Return unique suggestions (up to 8)
    seen = set()
    unique_suggestions = []
    for q in combined:
        if q not in seen:
            seen.add(q)
            unique_suggestions.append(q)
    return {"suggestions": unique_suggestions[:8]}
