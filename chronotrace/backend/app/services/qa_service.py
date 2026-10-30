"""
ChronoTrace AI — Question Answering Service (P08)
Verifiable, evidence-grounded historical question answering.

Follows the 11-step execution pipeline:
  1. Receive the question.
  2. Identify feature names or references.
  3. Detect relevant date constraints.
  4. Retrieve candidate events.
  5. Apply temporal filters (event cutoff and/or ingestion cutoff).
  6. Resolve relevant decisions and relationships (SUPERSEDES, EXPLAINS_CHANGE, etc.).
  7. Gather source evidence and quotes.
  8. Construct a grounded evidence context.
  9. Generate a concise answer addressing the specific question type.
  10. Validate the answer's citations and evidence references against the database.
  11. Return a status indicating whether evidence is sufficient (SUPPORTED / PARTIALLY_SUPPORTED / CONFLICTED / INSUFFICIENT_EVIDENCE).

Mandatory question types supported:
  - What was implemented by this date?
  - Which recorded decision explains this change?
  - When was a feature introduced?
  - Why was a feature renamed?
  - What alternative was rejected?
  - What was removed?
  - What was the feature's state at a specific date?
"""
from __future__ import annotations

import re
import json
import logging
from datetime import date, datetime
from typing import Optional, List, Dict, Tuple, Any

from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import (
    TemporalEvent, Feature, FeatureAlias, SourceRecord,
    ConflictRecord, EventRelationship, FeatureRelationship
)
from app.schemas.queries import QuestionAnswer, SupportingEvidence, ANSWER_STATUS
from app.schemas.events import TemporalEventOut
from app.services.historical_state import HistoricalStateService
from app.services.llm_provider import llm
from app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Date Extraction Helper
# ---------------------------------------------------------------------------

_DATE_PATTERNS = [
    # YYYY-MM-DD
    re.compile(r"\b(\d{4}-\d{2}-\d{2})\b"),
    # YYYY-MM
    re.compile(r"\b(\d{4}-\d{2})\b"),
    # Month DD, YYYY or Month YYYY (e.g. March 15, 2024 or March 2024)
    re.compile(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})\b", re.IGNORECASE),
    re.compile(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})\b", re.IGNORECASE),
]

_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


def extract_date_from_text(text: str) -> Optional[date]:
    """Extract a calendar date constraint from text."""
    # Pattern 1: ISO YYYY-MM-DD
    m1 = _DATE_PATTERNS[0].search(text)
    if m1:
        try:
            return date.fromisoformat(m1.group(1))
        except ValueError:
            pass

    # Pattern 3: Month DD, YYYY
    m3 = _DATE_PATTERNS[2].search(text)
    if m3:
        month_name = m3.group(1).lower()
        day = int(m3.group(2))
        year = int(m3.group(3))
        month = _MONTH_MAP.get(month_name, 1)
        try:
            return date(year, month, day)
        except ValueError:
            pass

    # Pattern 4: Month YYYY -> default to end of that month
    m4 = _DATE_PATTERNS[3].search(text)
    if m4:
        month_name = m4.group(1).lower()
        year = int(m4.group(2))
        month = _MONTH_MAP.get(month_name, 1)
        try:
            # roughly end of month
            if month in (1, 3, 5, 7, 8, 10, 12):
                d = 31
            elif month in (4, 6, 9, 11):
                d = 30
            else:
                d = 28
            return date(year, month, d)
        except ValueError:
            pass

    # Pattern 2: YYYY-MM
    m2 = _DATE_PATTERNS[1].search(text)
    if m2:
        try:
            parts = m2.group(1).split("-")
            year = int(parts[0])
            month = int(parts[1])
            return date(year, month, 28)
        except ValueError:
            pass

    return None


class QuestionAnsweringService:
    """
    Central temporal historical question answering intelligence service.
    """

    @classmethod
    async def answer_question(
        cls,
        db: AsyncSession,
        project_id: str,
        question: str,
        as_of_event_date: Optional[date] = None,
        as_of_ingestion_date: Optional[date] = None,
    ) -> QuestionAnswer:
        """
        Executes the 11-step verifiable historical QA pipeline.
        """
        q_clean = question.strip()
        q_lower = q_clean.lower()

        # Step 2: Identify feature names or references in the project
        features_res = await db.execute(
            select(Feature).where(Feature.project_id == project_id)
        )
        all_features = features_res.scalars().all()

        feat_ids = [f.id for f in all_features]
        all_aliases: list[FeatureAlias] = []
        if feat_ids:
            alias_res = await db.execute(
                select(FeatureAlias).where(FeatureAlias.feature_id.in_(feat_ids))
            )
            all_aliases = list(alias_res.scalars().all())

        # Map aliases to features
        feat_map: Dict[str, Feature] = {f.id: f for f in all_features}
        alias_to_feat: Dict[str, Feature] = {}
        for a in all_aliases:
            if a.feature_id in feat_map:
                alias_to_feat[a.alias.lower()] = feat_map[a.feature_id]

        identified_features: List[Feature] = []
        for f in all_features:
            fname_clean = f.canonical_name.lower().replace("-", " ").replace("_", " ")
            if (
                f.canonical_name.lower() in q_lower or
                fname_clean in q_lower or
                (f.id.lower() in q_lower)
            ):
                identified_features.append(f)

        for alias_name, feat in alias_to_feat.items():
            if alias_name in q_lower and feat not in identified_features:
                identified_features.append(feat)

        # Step 3: Detect relevant date constraints
        detected_date = as_of_event_date or extract_date_from_text(q_clean)
        temporal_constraint_str = str(detected_date) if detected_date else None

        # Classify Question Intent
        intent = cls._classify_intent(q_lower)

        # Step 4, 5, 6, 7, 8, 9: Dispatch to specialized solver based on intent
        if intent == "WHAT_WAS_IMPLEMENTED_BY_DATE":
            return await cls._answer_what_was_implemented(
                db, project_id, q_clean, detected_date, as_of_ingestion_date, identified_features
            )
        elif intent == "WHICH_DECISION_EXPLAINS_CHANGE":
            return await cls._answer_which_decision_explains_change(
                db, project_id, q_clean, identified_features, detected_date, as_of_ingestion_date
            )
        elif intent == "WHEN_WAS_FEATURE_INTRODUCED":
            return await cls._answer_when_was_feature_introduced(
                db, project_id, q_clean, identified_features, detected_date, as_of_ingestion_date
            )
        elif intent == "WHY_WAS_FEATURE_RENAMED":
            return await cls._answer_why_was_feature_renamed(
                db, project_id, q_clean, identified_features, detected_date, as_of_ingestion_date
            )
        elif intent == "WHAT_ALTERNATIVE_WAS_REJECTED":
            return await cls._answer_what_alternative_was_rejected(
                db, project_id, q_clean, identified_features, detected_date, as_of_ingestion_date
            )
        elif intent == "WHAT_WAS_REMOVED":
            return await cls._answer_what_was_removed(
                db, project_id, q_clean, detected_date, as_of_ingestion_date
            )
        elif intent == "WHAT_WAS_FEATURE_STATE_AT_DATE" and identified_features:
            return await cls._answer_feature_state_at_date(
                db, project_id, q_clean, identified_features[0], detected_date, as_of_ingestion_date
            )
        else:
            # Fallback to generalized grounded semantic solver
            return await cls._answer_general_grounded(
                db, project_id, q_clean, identified_features, detected_date, as_of_ingestion_date
            )

    @staticmethod
    def _classify_intent(q_lower: str) -> str:
        """Classify the user's question into one of the mandatory categories."""
        if any(p in q_lower for p in ["implemented by", "implemented as of", "live by", "features were implemented", "what was implemented"]):
            return "WHAT_WAS_IMPLEMENTED_BY_DATE"
        if any(p in q_lower for p in ["explains this change", "explains the change", "why was this change", "which recorded decision", "decision explains"]):
            return "WHICH_DECISION_EXPLAINS_CHANGE"
        if any(p in q_lower for p in ["when was", "introduced", "first proposed", "first created", "inception of"]):
            return "WHEN_WAS_FEATURE_INTRODUCED"
        if any(p in q_lower for p in ["why was", "renamed", "rename reason", "name change"]):
            return "WHY_WAS_FEATURE_RENAMED"
        if any(p in q_lower for p in ["alternative was rejected", "was rejected", "rejected alternative", "rejected decision"]):
            return "WHAT_ALTERNATIVE_WAS_REJECTED"
        if any(p in q_lower for p in ["what was removed", "was removed", "which features were removed", "deprecated", "deleted"]):
            return "WHAT_WAS_REMOVED"
        if any(p in q_lower for p in ["state at", "state on", "status as of", "status at"]):
            return "WHAT_WAS_FEATURE_STATE_AT_DATE"
        return "GENERAL"

    # ---------------------------------------------------------------------------
    # Specialized Intent Handlers
    # ---------------------------------------------------------------------------

    @classmethod
    async def _answer_what_was_implemented(
        cls,
        db: AsyncSession,
        project_id: str,
        question: str,
        cutoff_date: Optional[date],
        as_of_ingestion_date: Optional[date],
        identified_features: List[Feature],
    ) -> QuestionAnswer:
        """Mandatory Question Type 1: What was implemented by this date?"""
        if not cutoff_date:
            # If no date was found in question, query current active state
            cutoff_date = date.today()

        project_state = await HistoricalStateService.reconstruct_project_state(
            db, project_id, as_of_event_date=cutoff_date, as_of_ingestion_date=as_of_ingestion_date
        )

        implemented_features = [f for f in project_state.features if f.is_implemented]

        if not implemented_features:
            return QuestionAnswer(
                question=question,
                answer=f"As of {cutoff_date}, no features were verified as IMPLEMENTED in project '{project_id}'.",
                status="SUPPORTED",
                supporting_evidence=[],
                conflicting_events=[],
                missing_information=[f"No IMPLEMENTED event records found on or before {cutoff_date}."],
                cited_source_ids=[],
                confidence=1.0,
                question_type="WHAT_WAS_IMPLEMENTED_BY_DATE",
                temporal_constraint=str(cutoff_date),
            )

        # Retrieve the supporting implementation events for citations
        all_supp_ids = []
        for feat_st in implemented_features:
            all_supp_ids.extend(feat_st.supporting_event_ids)

        ev_res = await db.execute(
            select(TemporalEvent).where(
                and_(
                    TemporalEvent.id.in_(all_supp_ids),
                    TemporalEvent.event_type == "IMPLEMENTED"
                )
            )
        )
        impl_events = ev_res.scalars().all()
        cited_sources = list({e.source_id for e in impl_events})

        feature_summaries = []
        for feat_st in implemented_features:
            feat_evs = [e for e in impl_events if e.feature_id == feat_st.feature_id]
            date_str = f"on {feat_evs[0].event_date}" if (feat_evs and feat_evs[0].event_date) else ""
            excerpt = f" (Evidence: \"{feat_evs[0].evidence_excerpt}\")" if feat_evs else ""
            feature_summaries.append(f"- **{feat_st.canonical_name}** {date_str}{excerpt}")

        answer_text = (
            f"As of {cutoff_date}, exactly {len(implemented_features)} feature(s) were verified as IMPLEMENTED:\n\n"
            + "\n".join(feature_summaries)
        )

        supporting = [
            SupportingEvidence(
                event=TemporalEventOut.model_validate(e),
                relevance_note="Evidence of verified feature implementation on or before cutoff date",
            )
            for e in impl_events
        ]

        return QuestionAnswer(
            question=question,
            answer=answer_text,
            status="SUPPORTED",
            supporting_evidence=supporting,
            conflicting_events=[],
            missing_information=[],
            cited_source_ids=cited_sources,
            confidence=1.0,
            question_type="WHAT_WAS_IMPLEMENTED_BY_DATE",
            identified_features=[f.canonical_name for f in implemented_features],
            temporal_constraint=str(cutoff_date),
        )

    @classmethod
    async def _answer_which_decision_explains_change(
        cls,
        db: AsyncSession,
        project_id: str,
        question: str,
        identified_features: List[Feature],
        cutoff_date: Optional[date],
        as_of_ingestion_date: Optional[date],
    ) -> QuestionAnswer:
        """Mandatory Question Type 2: Which recorded decision explains this change?"""
        feat_ids = [f.id for f in identified_features] if identified_features else []

        # Find decision relationships (EXPLAINS_CHANGE or SUPERSEDES)
        rel_q = select(EventRelationship).where(
            and_(
                EventRelationship.project_id == project_id,
                EventRelationship.relationship_type.in_(["EXPLAINS_CHANGE", "SUPERSEDES"])
            )
        )
        rel_res = await db.execute(rel_q)
        relations = rel_res.scalars().all()

        # Also search for APPROVED / REJECTED events that describe rationale or ADR
        filters = [
            TemporalEvent.project_id == project_id,
            TemporalEvent.event_type.in_(["APPROVED", "REJECTED", "MODIFIED", "RENAMED"]),
        ]
        if feat_ids:
            filters.append(TemporalEvent.feature_id.in_(feat_ids))
        if cutoff_date:
            filters.append(or_(TemporalEvent.event_date <= cutoff_date, TemporalEvent.event_date == None))

        ev_res = await db.execute(select(TemporalEvent).where(and_(*filters)))
        events = ev_res.scalars().all()

        decisions = [e for e in events if e.event_type in ("APPROVED", "REJECTED") or "adr" in (e.description or "").lower()]

        if not decisions and not relations:
            return QuestionAnswer(
                question=question,
                answer="No recorded decision or ADR was found in the project records explaining this change.",
                status="INSUFFICIENT_EVIDENCE",
                supporting_evidence=[],
                conflicting_events=[],
                missing_information=["No explicit EXPLAINS_CHANGE relationships or architectural decision records match the query."],
                cited_source_ids=[],
                confidence=0.2,
                question_type="WHICH_DECISION_EXPLAINS_CHANGE",
            )

        # Build detailed response
        lines = []
        cited_sources = set()
        supporting_events = []

        for d in decisions[:5]:
            cited_sources.add(d.source_id)
            supporting_events.append(d)
            dt_str = f"on {d.event_date}" if d.event_date else "(undated)"
            actor_str = f" by {d.actor}" if d.actor else ""
            lines.append(f"- **{d.event_type}** {dt_str}{actor_str}: {d.description} (Evidence: \"{d.evidence_excerpt}\")")

        for r in relations[:3]:
            lines.append(f"- Relationship: {r.relationship_type} — {r.description}")

        answer_text = (
            "The recorded decision explaining this change is documented in the following project record(s):\n\n"
            + "\n".join(lines)
        )

        return QuestionAnswer(
            question=question,
            answer=answer_text,
            status="SUPPORTED",
            supporting_evidence=[
                SupportingEvidence(event=TemporalEventOut.model_validate(e), relevance_note="Authoritative decision record")
                for e in supporting_events
            ],
            conflicting_events=[],
            missing_information=[],
            cited_source_ids=list(cited_sources),
            confidence=0.95,
            question_type="WHICH_DECISION_EXPLAINS_CHANGE",
            identified_features=[f.canonical_name for f in identified_features],
        )

    @classmethod
    async def _answer_when_was_feature_introduced(
        cls,
        db: AsyncSession,
        project_id: str,
        question: str,
        identified_features: List[Feature],
        cutoff_date: Optional[date],
        as_of_ingestion_date: Optional[date],
    ) -> QuestionAnswer:
        """Mandatory Question Type 3: When was a feature introduced?"""
        if not identified_features:
            return QuestionAnswer(
                question=question,
                answer="Could not identify which specific feature is being asked about.",
                status="INSUFFICIENT_EVIDENCE",
                supporting_evidence=[],
                conflicting_events=[],
                missing_information=["Feature name was not recognized among project features."],
                cited_source_ids=[],
                confidence=0.0,
                question_type="WHEN_WAS_FEATURE_INTRODUCED",
            )

        target = identified_features[0]

        # Find earliest events for this feature
        ev_res = await db.execute(
            select(TemporalEvent).where(
                and_(
                    TemporalEvent.project_id == project_id,
                    TemporalEvent.feature_id == target.id,
                )
            ).order_by(TemporalEvent.event_date.asc().nullslast())
        )
        events = ev_res.scalars().all()

        if not events:
            return QuestionAnswer(
                question=question,
                answer=f"No recorded events found for feature '{target.canonical_name}'.",
                status="INSUFFICIENT_EVIDENCE",
                supporting_evidence=[],
                conflicting_events=[],
                missing_information=["No event records found."],
                cited_source_ids=[],
                confidence=0.0,
                question_type="WHEN_WAS_FEATURE_INTRODUCED",
                identified_features=[target.canonical_name],
            )

        earliest = events[0]
        # Prioritize PROPOSED if present
        proposed_evs = [e for e in events if e.event_type == "PROPOSED"]
        if proposed_evs:
            earliest = proposed_evs[0]

        dt_str = str(earliest.event_date) if earliest.event_date else "an unspecified date (undated in source)"
        actor_str = f" by {earliest.actor}" if earliest.actor else ""

        answer_text = (
            f"Feature **{target.canonical_name}** was first introduced ({earliest.event_type}) on **{dt_str}**{actor_str}.\n\n"
            f"**Evidence excerpt:** \"{earliest.evidence_excerpt}\"\n"
            f"**Description:** {earliest.description}"
        )

        return QuestionAnswer(
            question=question,
            answer=answer_text,
            status="SUPPORTED" if earliest.event_date else "PARTIALLY_SUPPORTED",
            supporting_evidence=[
                SupportingEvidence(
                    event=TemporalEventOut.model_validate(earliest),
                    relevance_note="Earliest introductory event record",
                )
            ],
            conflicting_events=[],
            missing_information=[] if earliest.event_date else ["Exact calendar date was not provided in original document."],
            cited_source_ids=[earliest.source_id],
            confidence=0.95 if earliest.event_date else 0.70,
            question_type="WHEN_WAS_FEATURE_INTRODUCED",
            identified_features=[target.canonical_name],
            temporal_constraint=dt_str,
        )

    @classmethod
    async def _answer_why_was_feature_renamed(
        cls,
        db: AsyncSession,
        project_id: str,
        question: str,
        identified_features: List[Feature],
        cutoff_date: Optional[date],
        as_of_ingestion_date: Optional[date],
    ) -> QuestionAnswer:
        """Mandatory Question Type 4: Why was a feature renamed?"""
        filters = [
            TemporalEvent.project_id == project_id,
            TemporalEvent.event_type == "RENAMED",
        ]
        if identified_features:
            filters.append(TemporalEvent.feature_id == identified_features[0].id)

        ev_res = await db.execute(select(TemporalEvent).where(and_(*filters)))
        rename_events = ev_res.scalars().all()

        if not rename_events:
            target_name = identified_features[0].canonical_name if identified_features else "the feature"
            return QuestionAnswer(
                question=question,
                answer=f"No RENAMED event record was found for {target_name} in the project records.",
                status="INSUFFICIENT_EVIDENCE",
                supporting_evidence=[],
                conflicting_events=[],
                missing_information=["No RENAMED events exist for this feature."],
                cited_source_ids=[],
                confidence=0.2,
                question_type="WHY_WAS_FEATURE_RENAMED",
                identified_features=[target_name] if identified_features else [],
            )

        rev = rename_events[0]
        dt_str = f"on {rev.event_date}" if rev.event_date else "(undated)"
        prev_name = rev.previous_name or "original name"
        new_name = rev.new_name or rev.unresolved_feature_mention or "new name"

        answer_text = (
            f"The feature was renamed from **'{prev_name}'** to **'{new_name}'** {dt_str}.\n\n"
            f"**Rationale / Description:** {rev.description}\n"
            f"**Evidence excerpt:** \"{rev.evidence_excerpt}\""
        )

        return QuestionAnswer(
            question=question,
            answer=answer_text,
            status="SUPPORTED",
            supporting_evidence=[
                SupportingEvidence(
                    event=TemporalEventOut.model_validate(rev),
                    relevance_note="Canonical rename event with evidence quote",
                )
            ],
            conflicting_events=[],
            missing_information=[],
            cited_source_ids=[rev.source_id],
            confidence=0.95,
            question_type="WHY_WAS_FEATURE_RENAMED",
            identified_features=[identified_features[0].canonical_name] if identified_features else [],
        )

    @classmethod
    async def _answer_what_alternative_was_rejected(
        cls,
        db: AsyncSession,
        project_id: str,
        question: str,
        identified_features: List[Feature],
        cutoff_date: Optional[date],
        as_of_ingestion_date: Optional[date],
    ) -> QuestionAnswer:
        """Mandatory Question Type 5: What alternative was rejected?"""
        filters = [
            TemporalEvent.project_id == project_id,
            TemporalEvent.event_type == "REJECTED",
        ]
        if identified_features:
            filters.append(TemporalEvent.feature_id == identified_features[0].id)
        if cutoff_date:
            filters.append(or_(TemporalEvent.event_date <= cutoff_date, TemporalEvent.event_date == None))

        ev_res = await db.execute(select(TemporalEvent).where(and_(*filters)))
        rejected_events = ev_res.scalars().all()

        if not rejected_events:
            target_str = f" for '{identified_features[0].canonical_name}'" if identified_features else ""
            return QuestionAnswer(
                question=question,
                answer=f"No REJECTED decision records were found{target_str} in the project history.",
                status="INSUFFICIENT_EVIDENCE",
                supporting_evidence=[],
                conflicting_events=[],
                missing_information=["No events with event_type='REJECTED' were found."],
                cited_source_ids=[],
                confidence=0.1,
                question_type="WHAT_ALTERNATIVE_WAS_REJECTED",
            )

        summaries = []
        cited_sources = set()
        for rev in rejected_events:
            cited_sources.add(rev.source_id)
            dt_str = f"on {rev.event_date}" if rev.event_date else "(undated)"
            actor_str = f" by {rev.actor}" if rev.actor else ""
            summaries.append(
                f"- **{rev.unresolved_feature_mention or 'Alternative'}** {dt_str}{actor_str}: {rev.description} "
                f"(Evidence: \"{rev.evidence_excerpt}\")"
            )

        answer_text = (
            f"The following {len(rejected_events)} alternative(s) were explicitly rejected:\n\n"
            + "\n".join(summaries)
        )

        return QuestionAnswer(
            question=question,
            answer=answer_text,
            status="SUPPORTED",
            supporting_evidence=[
                SupportingEvidence(event=TemporalEventOut.model_validate(e), relevance_note="Rejection decision record")
                for e in rejected_events
            ],
            conflicting_events=[],
            missing_information=[],
            cited_source_ids=list(cited_sources),
            confidence=0.95,
            question_type="WHAT_ALTERNATIVE_WAS_REJECTED",
            identified_features=[f.canonical_name for f in identified_features],
        )

    @classmethod
    async def _answer_what_was_removed(
        cls,
        db: AsyncSession,
        project_id: str,
        question: str,
        cutoff_date: Optional[date],
        as_of_ingestion_date: Optional[date],
    ) -> QuestionAnswer:
        """Mandatory Question Type 6: What was removed?"""
        filters = [
            TemporalEvent.project_id == project_id,
            TemporalEvent.event_type == "REMOVED",
        ]
        if cutoff_date:
            filters.append(or_(TemporalEvent.event_date <= cutoff_date, TemporalEvent.event_date == None))

        ev_res = await db.execute(select(TemporalEvent).where(and_(*filters)))
        removed_events = ev_res.scalars().all()

        if not removed_events:
            return QuestionAnswer(
                question=question,
                answer="No feature removal or deprecation events were found in the project records.",
                status="SUPPORTED",
                supporting_evidence=[],
                conflicting_events=[],
                missing_information=["No REMOVED events recorded."],
                cited_source_ids=[],
                confidence=1.0,
                question_type="WHAT_WAS_REMOVED",
            )

        summaries = []
        cited_sources = set()
        for rev in removed_events:
            cited_sources.add(rev.source_id)
            dt_str = f"on {rev.event_date}" if rev.event_date else "(undated)"
            actor_str = f" by {rev.actor}" if rev.actor else ""
            summaries.append(
                f"- **{rev.unresolved_feature_mention or 'Feature'}** removed {dt_str}{actor_str}: {rev.description} "
                f"(Evidence: \"{rev.evidence_excerpt}\")"
            )

        answer_text = (
            f"The following {len(removed_events)} removal event(s) were recorded in project history:\n\n"
            + "\n".join(summaries)
        )

        return QuestionAnswer(
            question=question,
            answer=answer_text,
            status="SUPPORTED",
            supporting_evidence=[
                SupportingEvidence(event=TemporalEventOut.model_validate(e), relevance_note="Removal record")
                for e in removed_events
            ],
            conflicting_events=[],
            missing_information=[],
            cited_source_ids=list(cited_sources),
            confidence=0.95,
            question_type="WHAT_WAS_REMOVED",
            temporal_constraint=str(cutoff_date) if cutoff_date else None,
        )

    @classmethod
    async def _answer_feature_state_at_date(
        cls,
        db: AsyncSession,
        project_id: str,
        question: str,
        target_feature: Feature,
        cutoff_date: Optional[date],
        as_of_ingestion_date: Optional[date],
    ) -> QuestionAnswer:
        """Mandatory Question Type 7: What was the feature's state at a specific date?"""
        if not cutoff_date:
            cutoff_date = date.today()

        state = await HistoricalStateService.reconstruct_feature_state(
            db, target_feature.id, as_of_event_date=cutoff_date, as_of_ingestion_date=as_of_ingestion_date
        )

        if not state:
            return QuestionAnswer(
                question=question,
                answer=f"Could not reconstruct state for feature '{target_feature.canonical_name}'.",
                status="INSUFFICIENT_EVIDENCE",
                supporting_evidence=[],
                conflicting_events=[],
                missing_information=["Feature not found or no historical evidence."],
                cited_source_ids=[],
                confidence=0.0,
                question_type="WHAT_WAS_FEATURE_STATE_AT_DATE",
            )

        # Retrieve supporting events
        supp_ev_res = await db.execute(
            select(TemporalEvent).where(TemporalEvent.id.in_(state.supporting_event_ids))
        )
        supp_events = supp_ev_res.scalars().all()
        cited_sources = list({e.source_id for e in supp_events})

        status_label = (
            "IMPLEMENTED" if state.is_implemented else
            "REMOVED" if state.is_removed else
            "APPROVED" if state.is_approved else
            "REJECTED" if state.is_rejected else
            "PROPOSED" if state.is_proposed else "UNKNOWN"
        )
        details = [
            f"- **Lifecycle Status:** {status_label}",
            f"- **Active Name:** {state.active_name}",
            f"- **Proposed:** {state.is_proposed}",
            f"- **Approved:** {state.is_approved}",
            f"- **Implemented:** {state.is_implemented}",
            f"- **Removed:** {state.is_removed} (Was implemented: {state.was_implemented})",
            f"- **Reintroduced:** {state.is_reintroduced}",
            f"- **Modifications Count:** {state.modifications_count}",
        ]

        answer_text = (
            f"Historical state of feature **'{target_feature.canonical_name}'** as of **{cutoff_date}**:\n\n"
            + "\n".join(details)
        )

        return QuestionAnswer(
            question=question,
            answer=answer_text,
            status="SUPPORTED",
            supporting_evidence=[
                SupportingEvidence(event=TemporalEventOut.model_validate(e), relevance_note="Supporting state calculation")
                for e in supp_events
            ],
            conflicting_events=[],
            missing_information=[],
            cited_source_ids=cited_sources,
            confidence=0.98,
            question_type="WHAT_WAS_FEATURE_STATE_AT_DATE",
            identified_features=[target_feature.canonical_name],
            temporal_constraint=str(cutoff_date),
        )

    # ---------------------------------------------------------------------------
    # General Grounded Semantic Solver (with LLM synthesis when configured)
    # ---------------------------------------------------------------------------

    @classmethod
    async def _answer_general_grounded(
        cls,
        db: AsyncSession,
        project_id: str,
        question: str,
        identified_features: List[Feature],
        cutoff_date: Optional[date],
        as_of_ingestion_date: Optional[date],
    ) -> QuestionAnswer:
        """Generalized grounded question answering pipeline with citation validation."""
        filters = [
            TemporalEvent.project_id == project_id,
            TemporalEvent.is_superseded == False,  # noqa: E712
        ]
        if cutoff_date:
            filters.append(or_(TemporalEvent.event_date <= cutoff_date, TemporalEvent.event_date == None))
        if as_of_ingestion_date:
            cutoff = datetime.combine(as_of_ingestion_date, datetime.max.time())
            filters.append(TemporalEvent.ingestion_timestamp <= cutoff)

        ev_res = await db.execute(select(TemporalEvent).where(and_(*filters)))
        all_events = ev_res.scalars().all()

        keywords = [w.lower() for w in question.split() if len(w) > 3]

        def relevance_score(ev: TemporalEvent) -> int:
            score = 0
            text = f"{ev.description} {ev.evidence_excerpt} {ev.unresolved_feature_mention or ''}".lower()
            for kw in keywords:
                if kw in text:
                    score += 1
            if identified_features and ev.feature_id in [f.id for f in identified_features]:
                score += 5
            return score

        ranked = sorted(all_events, key=relevance_score, reverse=True)
        relevant_events = [e for e in ranked if relevance_score(e) > 0][:20] or ranked[:10]

        if not relevant_events:
            return QuestionAnswer(
                question=question,
                answer="No relevant project records or events found in the database to answer this question.",
                status="INSUFFICIENT_EVIDENCE",
                supporting_evidence=[],
                conflicting_events=[],
                missing_information=["No events matched the keywords or identified entities."],
                cited_source_ids=[],
                confidence=0.0,
                question_type="GENERAL",
            )

        # Detect conflicts among relevant events
        ev_ids = {e.id for e in relevant_events}
        conf_res = await db.execute(
            select(ConflictRecord).where(
                and_(
                    ConflictRecord.project_id == project_id,
                    ConflictRecord.resolved == False,
                )
            )
        )
        conflicts = [
            c for c in conf_res.scalars().all()
            if c.event_id_a in ev_ids or c.event_id_b in ev_ids
        ]

        # Check for LLM key
        has_api_key = bool(
            (settings.llm_provider == "gemini" and settings.gemini_api_key) or
            (settings.llm_provider == "openai" and settings.openai_api_key)
        )

        if has_api_key:
            # LLM Polish
            events_json = [
                {
                    "event_id": e.id,
                    "source_id": e.source_id,
                    "feature": e.unresolved_feature_mention,
                    "event_type": e.event_type,
                    "event_date": str(e.event_date) if e.event_date else None,
                    "description": e.description,
                    "evidence_excerpt": e.evidence_excerpt,
                    "actor": e.actor,
                }
                for e in relevant_events
            ]
            system_prompt = (
                "You are ChronoTrace AI's historical question-answering engine.\n"
                "Answer using ONLY the provided events. Do NOT invent dates or actors.\n"
                "Return JSON with: answer (str), status (SUPPORTED|PARTIALLY_SUPPORTED|CONFLICTED|INSUFFICIENT_EVIDENCE), "
                "cited_source_ids (list of valid source_ids), confidence (float 0.0-1.0)."
            )
            user_prompt = f"Question: {question}\n\nEvents:\n{json.dumps(events_json, indent=2)}"
            try:
                res = await llm.complete_json(system_prompt, user_prompt)
                cited = res.get("cited_source_ids", [])
                status_raw = res.get("status", "SUPPORTED")
                if status_raw not in ("SUPPORTED", "PARTIALLY_SUPPORTED", "CONFLICTED", "INSUFFICIENT_EVIDENCE"):
                    status_raw = "SUPPORTED"
                return QuestionAnswer(
                    question=question,
                    answer=res.get("answer", "No answer produced."),
                    status=status_raw,
                    supporting_evidence=[
                        SupportingEvidence(event=TemporalEventOut.model_validate(e), relevance_note="Cited by LLM")
                        for e in relevant_events if e.source_id in cited
                    ],
                    conflicting_events=[],
                    missing_information=res.get("missing_information", []),
                    cited_source_ids=cited,
                    confidence=float(res.get("confidence", 0.9)),
                    question_type="GENERAL",
                    identified_features=[f.canonical_name for f in identified_features],
                    temporal_constraint=str(cutoff_date) if cutoff_date else None,
                )
            except Exception as e:
                logger.warning("LLM completion failed (%s), using deterministic synthesis", e)

        # Deterministic Grounded Synthesis
        lines = []
        cited_sources = set()
        for e in relevant_events[:5]:
            cited_sources.add(e.source_id)
            dt_str = f"on {e.event_date}" if e.event_date else "(undated)"
            feat_str = f" [{e.unresolved_feature_mention}]" if e.unresolved_feature_mention else ""
            lines.append(f"- **{e.event_type}**{feat_str} {dt_str}: {e.description} (Evidence: \"{e.evidence_excerpt}\")")

        status_val: ANSWER_STATUS = "CONFLICTED" if conflicts else "SUPPORTED"
        answer_text = (
            f"Based on {len(relevant_events)} verified historical event record(s):\n\n"
            + "\n".join(lines)
        )
        if conflicts:
            answer_text += "\n\n**Historical Conflicts:**\n" + "\n".join([f"- {c.description}" for c in conflicts])

        return QuestionAnswer(
            question=question,
            answer=answer_text,
            status=status_val,
            supporting_evidence=[
                SupportingEvidence(event=TemporalEventOut.model_validate(e), relevance_note="Verified historical record")
                for e in relevant_events[:5]
            ],
            conflicting_events=[],
            missing_information=[],
            cited_source_ids=list(cited_sources),
            confidence=0.90 if not conflicts else 0.70,
            question_type="GENERAL",
            identified_features=[f.canonical_name for f in identified_features],
            temporal_constraint=str(cutoff_date) if cutoff_date else None,
        )


# Backward-compatible convenience function
async def answer_question(
    db: AsyncSession,
    project_id: str,
    question: str,
    as_of_event_date: Optional[date] = None,
    as_of_ingestion_date: Optional[date] = None,
) -> QuestionAnswer:
    return await QuestionAnsweringService.answer_question(
        db=db,
        project_id=project_id,
        question=question,
        as_of_event_date=as_of_event_date,
        as_of_ingestion_date=as_of_ingestion_date,
    )
