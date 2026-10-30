"""Knowledge graph routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services.graph.knowledge_graph import rebuild_graph, get_knowledge_graph

router = APIRouter()


@router.get("/")
def get_graph(db: Session = Depends(get_db)):
    """Return the full knowledge graph as React Flow-compatible JSON."""
    graph = get_knowledge_graph()
    if graph._built_at is None:
        graph.build_from_db(db)
    return graph.to_json_graph()


@router.post("/rebuild")
def rebuild_knowledge_graph(db: Session = Depends(get_db)):
    """Force a full rebuild of the knowledge graph from the database."""
    graph = rebuild_graph(db)
    return {
        "message": "Graph rebuilt successfully.",
        "nodes": graph.graph.number_of_nodes(),
        "edges": graph.graph.number_of_edges(),
    }
