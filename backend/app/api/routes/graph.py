"""Knowledge graph routes."""

from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services.graph.knowledge_graph import rebuild_graph, get_knowledge_graph

router = APIRouter()


@router.get("/")
def get_graph(
    feature_id: Optional[str] = Query(None, description="Optional feature ID to isolate its sub-graph"),
    only_with_events: bool = Query(False, description="Filter only nodes that have events"),
    db: Session = Depends(get_db),
):
    """Return the knowledge graph as React Flow-compatible JSON, optionally filtered by feature."""
    graph = get_knowledge_graph()
    if graph._built_at is None:
        graph.build_from_db(db)
    return graph.to_json_graph(feature_id=feature_id, only_with_events=only_with_events)


@router.post("/rebuild")
def rebuild_knowledge_graph(db: Session = Depends(get_db)):
    """Force a full rebuild of the knowledge graph from the database."""
    graph = rebuild_graph(db)
    return {
        "message": "Graph rebuilt successfully.",
        "nodes": graph.graph.number_of_nodes(),
        "edges": graph.graph.number_of_edges(),
    }
