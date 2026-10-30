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

        # Modules
        for m in db.query(Module).all():
            self._add_node(f"module:{m.id}", "module", m.canonical_name, module_id=m.id)

        # Features & Module containment
        for f in db.query(Feature).all():
            self._add_node(
                f"feature:{f.id}", "feature", f.canonical_name,
                feature_id=f.id, status=f.current_status,
                first_seen=f.first_seen_date.isoformat() if f.first_seen_date else None,
                aliases_count=len(f.aliases),
            )
            # Module -> Feature (natural architectural hierarchy)
            if f.module_id:
                self._add_edge(f"module:{f.module_id}", f"feature:{f.id}", "MODULE_CONTAINS_FEATURE")

        # Documents
        for d in db.query(Document).all():
            self._add_node(
                f"document:{d.id}", "document", d.original_filename,
                document_id=d.id, file_type=d.file_type,
                file_size=d.file_size_bytes,
            )

        # Events & Feature relationships
        all_events = db.query(Event).all()
        # Group events by feature to create chronological sequence edges (EVENT_FOLLOWS_EVENT)
        feature_events_map: Dict[str, List[Event]] = {}

        for e in all_events:
            self._add_node(
                f"event:{e.id}", "event", e.title,
                event_id=e.id, event_type=e.event_type,
                decision_status=e.decision_status,
                event_date=e.event_date.isoformat() if e.event_date else None,
                confidence=e.confidence_score,
                has_conflict=e.has_conflict,
                source_document_filename=e.source_document.original_filename if e.source_document else None,
            )
            # Feature -> Event (natural lifecycle hierarchy)
            if e.feature_id:
                self._add_edge(f"feature:{e.feature_id}", f"event:{e.id}", "FEATURE_HAS_EVENT")
                feature_events_map.setdefault(e.feature_id, []).append(e)

            # Event -> Document (evidence citation)
            if e.source_document_id:
                self._add_edge(
                    f"event:{e.id}", f"document:{e.source_document_id}", "EVENT_SUPPORTED_BY"
                )

        # Chronological sequence between events of the same feature
        for feat_id, ev_list in feature_events_map.items():
            sorted_evs = sorted(
                ev_list,
                key=lambda x: (x.event_date or datetime.min, x.recorded_at or datetime.min)
            )
            for i in range(len(sorted_evs) - 1):
                self._add_edge(
                    f"event:{sorted_evs[i].id}",
                    f"event:{sorted_evs[i+1].id}",
                    "EVENT_FOLLOWS_EVENT",
                )

        # Explicit event relationships recorded in DB
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
        # Check successors (FEATURE_HAS_EVENT) and predecessors
        candidates = list(self.graph.successors(feature_node)) + list(self.graph.predecessors(feature_node))
        for node in candidates:
            data = self.graph.nodes.get(node, {})
            if data.get("node_type") == "event" and "event_id" in data:
                event_ids.append(data["event_id"])
        return list(set(event_ids))

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

    def to_json_graph(self, limit_nodes: int = 400, feature_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Serialise the graph to a React Flow-compatible JSON structure.
        Optionally isolates the subgraph for a specific *feature_id*.
        """
        nodes = []
        edges = []

        if feature_id:
            feat_node = f"feature:{feature_id}"
            if feat_node in self.graph:
                # Include feature node
                included = {feat_node}

                # Include parent modules
                for pred in self.graph.predecessors(feat_node):
                    if self.graph.nodes[pred].get("node_type") == "module":
                        included.add(pred)

                # Include all events linked to this feature
                for succ in self.graph.successors(feat_node):
                    if self.graph.nodes[succ].get("node_type") == "event":
                        included.add(succ)

                # Include documents linked to those events, plus sequential follow events
                event_nodes = [n for n in included if self.graph.nodes[n].get("node_type") == "event"]
                for en in event_nodes:
                    for succ in self.graph.successors(en):
                        if self.graph.nodes[succ].get("node_type") in ("document", "event"):
                            included.add(succ)

                for nid in included:
                    data = self.graph.nodes[nid]
                    nodes.append({"id": nid, "label": data.get("label", nid), **data})

                for src, dst, data in self.graph.edges(data=True):
                    if src in included and dst in included:
                        edges.append({"source": src, "target": dst, **data})

                return {"nodes": nodes, "edges": edges, "filtered_feature_id": feature_id}

        # Global graph view: Prioritize connected nodes with active relationships
        all_nodes = list(self.graph.nodes(data=True))
        sorted_nodes = sorted(
            all_nodes,
            key=lambda x: (
                self.graph.degree(x[0]) > 0,  # Connected nodes first!
                {"module": 4, "feature": 3, "event": 2, "document": 1, "person": 0}.get(
                    x[1].get("node_type", ""), 0
                ),
                self.graph.degree(x[0]),  # Higher degree first
            ),
            reverse=True,
        )
        included = set()
        for nid, data in sorted_nodes[:limit_nodes]:
            degree = self.graph.degree(nid)
            nodes.append({
                "id": nid,
                "label": data.get("label", nid),
                "degree": degree,
                "is_isolated": degree == 0,
                **data,
            })
            included.add(nid)

        for src, dst, data in self.graph.edges(data=True):
            if src in included and dst in included:
                edges.append({"source": src, "target": dst, **data})

        return {"nodes": nodes, "edges": edges, "filtered_feature_id": None}


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

