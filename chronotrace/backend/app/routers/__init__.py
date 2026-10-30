from app.routers.ingestion import router as ingestion_router
from app.routers.events import router as events_router
from app.routers.features import router as features_router
from app.routers.timeline import router as timeline_router
from app.routers.qa import router as qa_router
from app.routers.graph import router as graph_router
from app.routers.projects import router as projects_router
from app.routers.conflicts import router as conflicts_router
from app.routers.dashboard import router as dashboard_router

__all__ = [
    "ingestion_router",
    "events_router",
    "features_router",
    "timeline_router",
    "qa_router",
    "graph_router",
    "projects_router",
    "conflicts_router",
    "dashboard_router",
]
