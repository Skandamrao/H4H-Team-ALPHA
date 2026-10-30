"""
ChronoTrace AI — Graph Service (P07)
Provides temporal knowledge graph construction and query services.

Supported Relationship Types:
  - PROPOSES: Source -> Event / Event -> Feature
  - APPROVES: Decision Event -> Feature
  - REJECTS: Decision Event -> Feature
  - IMPLEMENTS: Implementation Event -> Decision Event / Feature
  - EXPLAINS_CHANGE: Modification Event -> Prior Event / Decision
  - RENAMES: Rename Event -> Feature
  - MODIFIES: Modification Event -> Feature
  - REMOVES: Removal Event -> Feature
  - DEPENDS_ON: Feature -> Target Feature
  - SUPERSEDES: Event -> Prior Event
  - CONTRADICTS: Event <-> Conflicting Event
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import (
    Feature, TemporalEvent, SourceRecord, FeatureAlias,
    FeatureRelationship, EventRelationship, ConflictRecord
)
from app.schemas.queries import (
    TemporalGraphOut, GraphNode, GraphEdge, FeatureTimeline
)

logger = logging.getLogger(__name__)


class GraphService:
    """
    Temporal knowledge graph construction and relational query engine.
    """

    @classmethod
    async def get_feature_events(
        cls,
        db: AsyncSession,
        feature_id: str,
        as_of_event_date: Optional[date] = None,
    ) -> List[TemporalEvent]:
        """Query all events associated with a feature up to an optional event date cutoff."""
        filters = [TemporalEvent.feature_id == feature_id]
        if as_of_event_date:
            filters.append(
                (TemporalEvent.event_date <= as_of_event_date) | (TemporalEvent.event_date == None)  # noqa: E711
            )
        res = await db.execute(
            select(TemporalEvent).where(and_(*filters)).order_by(TemporalEvent.event_date)
        )
        return list(res.scalars().all())

    @classmethod
    async def get_feature_aliases(
        cls,
        db: AsyncSession,
        feature_id: str,
    ) -> List[FeatureAlias]:
        """Query all alias records for a feature."""
        res = await db.execute(
            select(FeatureAlias).where(FeatureAlias.feature_id == feature_id)
        )
        return list(res.scalars().all())

    @classmethod
    async def get_decision_to_implementation(
        cls,
        db: AsyncSession,
        feature_id: str,
    ) -> Dict[str, Any]:
        """
        Query the explicit link between an APPROVED decision and its subsequent IMPLEMENTATION.
        Returns the decision event, implementation event, and time delta.
        """
        events = await cls.get_feature_events(db, feature_id)
        approvals = [e for e in events if e.event_type == "APPROVED" and not e.is_superseded]
        implementations = [e for e in events if e.event_type == "IMPLEMENTED"]

        pairs = []
        for app in approvals:
            for impl in implementations:
                if impl.event_date and app.event_date and impl.event_date >= app.event_date:
                    delta_days = (impl.event_date - app.event_date).days
                    pairs.append({
                        "decision_event_id": app.id,
                        "decision_date": str(app.event_date),
                        "decision_description": app.description,
                        "implementation_event_id": impl.id,
                        "implementation_date": str(impl.event_date),
                        "implementation_description": impl.description,
                        "latency_days": delta_days,
                    })

        return {
            "feature_id": feature_id,
            "decision_to_implementation_links": pairs,
            "has_unimplemented_approvals": len(approvals) > len(implementations),
        }

    @classmethod
    async def get_change_to_decision(
        cls,
        db: AsyncSession,
        feature_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Finds modification or rename events linked to prior decisions explaining the change.
        """
        events = await cls.get_feature_events(db, feature_id)
        changes = [e for e in events if e.event_type in ("MODIFIED", "RENAMED")]
        decisions = [e for e in events if e.event_type in ("APPROVED", "REJECTED")]

        motivating_links = []
        for chg in changes:
            # Look for explicit event relationships
            rel_res = await db.execute(
                select(EventRelationship).where(
                    EventRelationship.from_event_id == chg.id,
                    EventRelationship.relationship_type.in_(["EXPLAINS_CHANGE", "CAUSED_BY"]),
                )
            )
            explicit_rels = rel_res.scalars().all()
            for r in explicit_rels:
                motivating_links.append({
                    "change_event_id": chg.id,
                    "change_description": chg.description,
                    "motivating_event_id": r.to_event_id,
                    "relationship_type": r.relationship_type,
                    "evidence": r.description,
                })

        return motivating_links

    @classmethod
    async def get_feature_dependencies(
        cls,
        db: AsyncSession,
        feature_id: str,
    ) -> List[Dict[str, Any]]:
        """Query direct dependencies for a feature."""
        res = await db.execute(
            select(FeatureRelationship).where(
                FeatureRelationship.source_feature_id == feature_id,
                FeatureRelationship.relationship_type == "DEPENDS_ON",
            )
        )
        rels = res.scalars().all()
        results = []
        for r in rels:
            target_feat = await db.get(Feature, r.target_feature_id)
            results.append({
                "source_feature_id": feature_id,
                "target_feature_id": r.target_feature_id,
                "target_feature_name": target_feat.canonical_name if target_feat else "Unknown",
                "evidence_excerpt": r.evidence_excerpt,
            })
        return results

    @classmethod
    async def get_project_graph(
        cls,
        db: AsyncSession,
        project_id: str,
        as_of_event_date: Optional[date] = None,
        as_of_ingestion_date: Optional[date] = None,
    ) -> TemporalGraphOut:
        """
        Build full project knowledge graph with nodes and semantically typed edges.
        """
        nodes: List[GraphNode] = []
        edges: List[GraphEdge] = []
        edge_id_seq = 1

        # 1. Feature Nodes
        feat_res = await db.execute(select(Feature).where(Feature.project_id == project_id))
        features = feat_res.scalars().all()
        for f in features:
            nodes.append(GraphNode(
                id=f"feat_{f.id}",
                label=f.canonical_name,
                type="feature",
                data={
                    "feature_id": f.id,
                    "is_implemented": f.is_implemented,
                    "is_approved": f.is_approved,
                    "is_removed": f.is_removed,
                }
            ))

        # 2. Event Nodes & Edges to Features
        ev_filters = [TemporalEvent.project_id == project_id]
        if as_of_event_date:
            ev_filters.append(
                (TemporalEvent.event_date <= as_of_event_date) | (TemporalEvent.event_date == None)  # noqa: E711
            )
        if as_of_ingestion_date:
            ingestion_cutoff = datetime.combine(as_of_ingestion_date, datetime.max.time())
            ev_filters.append(TemporalEvent.ingestion_timestamp <= ingestion_cutoff)

        ev_res = await db.execute(select(TemporalEvent).where(and_(*ev_filters)))
        events = ev_res.scalars().all()

        for e in events:
            # Event node
            nodes.append(GraphNode(
                id=f"ev_{e.id}",
                label=f"[{e.event_type}] {e.description[:40]}...",
                type="decision" if e.event_type in ("APPROVED", "REJECTED") else "event",
                data={
                    "event_id": e.id,
                    "event_type": e.event_type,
                    "event_date": str(e.event_date) if e.event_date else None,
                    "actor": e.actor,
                    "evidence_excerpt": e.evidence_excerpt,
                    "is_superseded": e.is_superseded,
                }
            ))

            # Edge to Feature
            if e.feature_id:
                rel_type = e.event_type
                if rel_type == "PROPOSED":
                    rel_type = "PROPOSES"
                elif rel_type == "APPROVED":
                    rel_type = "APPROVES"
                elif rel_type == "REJECTED":
                    rel_type = "REJECTS"
                elif rel_type == "IMPLEMENTED":
                    rel_type = "IMPLEMENTS"
                elif rel_type == "RENAMED":
                    rel_type = "RENAMES"
                elif rel_type == "MODIFIED":
                    rel_type = "MODIFIES"
                elif rel_type == "REMOVED":
                    rel_type = "REMOVES"
                elif rel_type == "DEPENDENCY_ADDED":
                    rel_type = "DEPENDS_ON"

                edges.append(GraphEdge(
                    id=f"edge_{edge_id_seq}",
                    source=f"ev_{e.id}",
                    target=f"feat_{e.feature_id}",
                    relationship_type=rel_type,
                    description=e.description,
                    data={"evidence_excerpt": e.evidence_excerpt},
                ))
                edge_id_seq += 1

            # Supersedes edge
            if e.supersedes_event_id:
                edges.append(GraphEdge(
                    id=f"edge_{edge_id_seq}",
                    source=f"ev_{e.id}",
                    target=f"ev_{e.supersedes_event_id}",
                    relationship_type="SUPERSEDES",
                    description=f"Event {e.id} supersedes earlier decision {e.supersedes_event_id}",
                    data={"evidence_excerpt": e.evidence_excerpt},
                ))
                edge_id_seq += 1

        # 3. Explicit Event Relationships
        er_res = await db.execute(select(EventRelationship).where(EventRelationship.project_id == project_id))
        event_relationships = er_res.scalars().all()
        for er in event_relationships:
            edges.append(GraphEdge(
                id=f"edge_{edge_id_seq}",
                source=f"ev_{er.from_event_id}",
                target=f"ev_{er.to_event_id}",
                relationship_type=er.relationship_type,
                description=er.description,
                data={},
            ))
            edge_id_seq += 1

        # 4. Feature Dependencies (Feature -> Feature)
        fr_res = await db.execute(select(FeatureRelationship).where(FeatureRelationship.project_id == project_id))
        feature_relationships = fr_res.scalars().all()
        for fr in feature_relationships:
            edges.append(GraphEdge(
                id=f"edge_{edge_id_seq}",
                source=f"feat_{fr.source_feature_id}",
                target=f"feat_{fr.target_feature_id}",
                relationship_type=fr.relationship_type,
                description=fr.relationship_type,
                data={"evidence_excerpt": fr.evidence_excerpt},
            ))
            edge_id_seq += 1

        # 5. Conflicts as CONTRADICTS edges
        conf_res = await db.execute(
            select(ConflictRecord).where(ConflictRecord.project_id == project_id, ConflictRecord.resolved == False)  # noqa: E712
        )
        conflicts = conf_res.scalars().all()
        for c in conflicts:
            edges.append(GraphEdge(
                id=f"edge_{edge_id_seq}",
                source=f"ev_{c.event_id_a}",
                target=f"ev_{c.event_id_b}",
                relationship_type="CONTRADICTS",
                description=c.description,
                data={"conflict_type": c.conflict_type},
            ))
            edge_id_seq += 1

        return TemporalGraphOut(
            project_id=project_id,
            as_of_event_date=as_of_event_date,
            as_of_ingestion_date=as_of_ingestion_date,
            nodes=nodes,
            edges=edges,
        )
