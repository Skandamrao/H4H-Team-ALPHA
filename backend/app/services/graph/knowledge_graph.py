"""
Temporal Knowledge Graph Service.

Uses NetworkX to build and query an in-memory directed graph that mirrors
the SQLite database. This graph supports fast relationship traversal and
can be extended to Neo4j in a future iteration.

Node types:   feature | module | event | decision | document | person
Edge types:   PROJECT_HAS_FEATURE | FEATURE_BELONGS_TO_MODULE |
              EVENT_AFFECTS_FEATURE | EVENT_SUPPORTED_BY_DOCUMENT |
              DECISION_RELATES_TO_FEATURE | FEATURE_RENAMED_FROM |
              EVENT_FOLLOWS_EVENT | EVENT_SUPERSEDES_EVENT
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import networkx as nx
from sqlalchemy.orm import Session

from app.models.models import Feature, Event, Module, Document, Person, EventRelationship, FeatureAlias

logger = logging.getLogger(__name__)


class TemporalKnowledgeGraph:
    """
    In-memory directed graph backed by NetworkX.

    The graph is rebuilt from the database on demand (or on first access).
    In production with Neo4j, this class would issue Cypher queries instead.
    """

    def __init__(self) -> None:
        self.graph: nx.DiGraph = nx.DiGraph()
        self._built_at: Optional[datetime] = None

    def _add_node(self, node_id: str, node_type: str, label: str, **props: Any) -> None:
        self.graph.add_node(node_id, node_type=node_type, label=label, **props)

    def _add_edge(self, src: str, dst: str, rel_type: str, **props: Any) -> None:
        self.graph.add_edge(src, dst, relationship_type=rel_type, **props)

    # ── Graph construction ────────────────────────────────────────────────────

    def build_from_db(self, db: Session) -> None:
        """Rebuild the entire graph from the current database state."""
        self.graph.clear()

        # Features
        for f in db.query(Feature).all():
            self._add_node(
                f"feature:{f.id}", "feature", f.canonical_name,
                feature_id=f.id, status=f.current_status,
            )

        # Modules
        for m in db.query(Module).all():
            self._add_node(f"module:{m.id}", "module", m.canonical_name, module_id=m.id)

        # Documents
        for d in db.query(Document).all():
            self._add_node(
                f"document:{d.id}", "document", d.original_filename,
                document_id=d.id, file_type=d.file_type,
            )

        # Events
        for e in db.query(Event).all():
            self._add_node(
                f"event:{e.id}", "event", e.title,
                event_id=e.id, event_type=e.event_type,
                event_date=e.event_date.isoformat() if e.event_date else None,
                confidence=e.confidence_score,
            )
            # Event → Feature
            if e.feature_id:
                self._add_edge(f"event:{e.id}", f"feature:{e.feature_id}", "EVENT_AFFECTS_FEATURE")
            # Event → Document
            if e.source_document_id:
                self._add_edge(
                    f"event:{e.id}", f"document:{e.source_document_id}", "EVENT_SUPPORTED_BY_DOCUMENT"
                )

        # Feature → Module
        for f in db.query(Feature).filter(Feature.module_id.isnot(None)).all():
            self._add_edge(f"feature:{f.id}", f"module:{f.module_id}", "FEATURE_BELONGS_TO_MODULE")

        # Event relationships
        for rel in db.query(EventRelationship).all():
            self._add_edge(
                f"event:{rel.source_event_id}",
                f"event:{rel.target_event_id}",
                rel.relationship_type,
            )

        self._built_at = datetime.utcnow()
        logger.info(
            "Knowledge graph built: %d nodes, %d edges.",
            self.graph.number_of_nodes(), self.graph.number_of_edges(),
        )

    # ── Graph queries ─────────────────────────────────────────────────────────

    def get_feature_events(self, feature_id: str) -> List[str]:
        """Return event IDs for all events that affect *feature_id*."""
        feature_node = f"feature:{feature_id}"
        event_ids = []
        for node in self.graph.predecessors(feature_node):
            data = self.graph.nodes[node]
            if data.get("node_type") == "event":
                event_ids.append(data["event_id"])
        return event_ids

    def get_feature_documents(self, feature_id: str) -> List[str]:
        """Return document IDs for all documents that mention *feature_id*."""
        event_ids = self.get_feature_events(feature_id)
        doc_ids = set()
        for eid in event_ids:
            event_node = f"event:{eid}"
            for successor in self.graph.successors(event_node):
                data = self.graph.nodes.get(successor, {})
                if data.get("node_type") == "document":
                    doc_ids.add(data["document_id"])
        return list(doc_ids)

    def get_related_events(self, event_id: str, max_depth: int = 2) -> List[str]:
        """Return IDs of events reachable within *max_depth* hops."""
        event_node = f"event:{event_id}"
        if event_node not in self.graph:
            return []
        related = set()
        for depth in range(1, max_depth + 1):
            for node in nx.ego_graph(self.graph, event_node, radius=depth, undirected=True).nodes():
                if node != event_node and self.graph.nodes[node].get("node_type") == "event":
                    related.add(self.graph.nodes[node]["event_id"])
        return list(related)

    def to_json_graph(self, limit_nodes: int = 300) -> Dict[str, Any]:
        """
        Serialise the graph to a React Flow-compatible JSON structure.
        Limits to *limit_nodes* nodes to keep the payload manageable.
        """
        nodes = []
        edges = []

        all_nodes = list(self.graph.nodes(data=True))
        # Prioritise feature and module nodes for display
        sorted_nodes = sorted(
            all_nodes,
            key=lambda x: {"feature": 0, "module": 1, "event": 2, "document": 3, "person": 4}.get(
                x[1].get("node_type", ""), 5
            ),
        )
        included = set()
        for nid, data in sorted_nodes[:limit_nodes]:
            nodes.append({"id": nid, "label": data.get("label", nid), **data})
            included.add(nid)

        for src, dst, data in self.graph.edges(data=True):
            if src in included and dst in included:
                edges.append({"source": src, "target": dst, **data})

        return {"nodes": nodes, "edges": edges}


# Module-level singleton
_graph_instance: Optional[TemporalKnowledgeGraph] = None


def get_knowledge_graph() -> TemporalKnowledgeGraph:
    global _graph_instance
    if _graph_instance is None:
        _graph_instance = TemporalKnowledgeGraph()
    return _graph_instance


def rebuild_graph(db: Session) -> TemporalKnowledgeGraph:
    """Force a full graph rebuild from the current database state."""
    graph = get_knowledge_graph()
    graph.build_from_db(db)
    return graph

