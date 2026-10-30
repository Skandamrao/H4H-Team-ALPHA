"""
P05 Temporal Event Extraction Engine Test Suite
Validates all requirements for Stage P05:
  1. Proposal Extraction (Rule B — Proposal ≠ Approval)
  2. Approval Extraction (Rule A — Approval ≠ Implementation)
  3. Implementation Extraction (Merged PR / Production release)
  4. Rejection Extraction (ADR sign-off / Rejection)
  5. Rename Extraction (capturing both previous_name and new_name)
  6. Removal / Deprecation Extraction (REMOVED)
  7. Dependency Extraction (DEPENDENCY_ADDED)
  8. Modification Extraction (MODIFIED)
  9. Strict Date Separation (Rule C — No fake dates or defaults to now)
  10. Verbatim Evidence Compulsory (Rule H — evidence_excerpt must exist in content)
  11. Zero Hallucination (Rule G — Unknown actors remain None)
  12. Schema Invariant Enforcement (TemporalEventCreate model validators)
  13. Multi-Event Meeting Record Extraction
"""
from __future__ import annotations

import pytest
import uuid
from datetime import date

from app.schemas.events import TemporalEventCreate
from app.services.extraction_service import extract_events_from_record, EventExtractor
from app.services.rule_extractor import extract_rule_based_events


# ---------------------------------------------------------------------------
# Test 1: Proposal Extraction (Rule B)
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_01_proposal_extraction_rule_b():
    content = """
    Sprint Planning Notes:
    Dev Patel suggested adding CSV export functionality to the dashboard reports section.
    No decision made. Needs design review first.
    """
    events = await extract_events_from_record(
        project_id="proj-p05",
        source_id="src-01",
        record_type="meeting_notes",
        title="Sprint Planning",
        source_date=date(2024, 1, 10),
        source_date_raw="January 10, 2024",
        content=content,
    )
    assert len(events) >= 1
    proposal = [e for e in events if e.event_type == "PROPOSED"][0]
    assert proposal.event_type == "PROPOSED"
    assert "CSV Export" in proposal.unresolved_feature_mention or "Data Export" in proposal.unresolved_feature_mention or "csv" in proposal.description.lower()
    assert proposal.actor == "Dev Patel"
    # Rule B: must NOT be APPROVED
    assert not any(e.event_type == "APPROVED" for e in events)


# ---------------------------------------------------------------------------
# Test 2: Approval Extraction (Rule A: Approval ≠ Implementation)
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_02_approval_extraction_rule_a():
    content = """
    Decision: proposal accepted for Sprint 3 (starting Feb 5, 2024). Ravi Kumar assigned as owner.
    Note: No implementation has started yet — this is approval only.
    """
    events = await extract_events_from_record(
        project_id="proj-p05",
        source_id="src-02",
        record_type="meeting_notes",
        title="Auth Module Review",
        source_date=date(2024, 1, 10),
        source_date_raw="January 10, 2024",
        content=content,
    )
    assert len(events) >= 1
    approval = [e for e in events if e.event_type == "APPROVED"][0]
    assert approval.event_type == "APPROVED"
    assert approval.actor == "Ravi Kumar"
    # Rule A: must NOT be IMPLEMENTED
    assert not any(e.event_type == "IMPLEMENTED" for e in events)


# ---------------------------------------------------------------------------
# Test 3: Implementation Extraction
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_03_implementation_extraction():
    content = """
    ## Data Export Feature v1.0 — Released March 5, 2024
    ### Shipped
    - CSV export from dashboard reports is now live in production.
    - Implementation completed: March 3, 2024.
    - PR #502 merged into main.
    """
    events = await extract_events_from_record(
        project_id="proj-p05",
        source_id="src-03",
        record_type="changelog",
        title="Release Notes v1.0",
        source_date=date(2024, 3, 5),
        source_date_raw="March 5, 2024",
        content=content,
    )
    impl_events = [e for e in events if e.event_type == "IMPLEMENTED"]
    assert len(impl_events) >= 1
    impl = impl_events[0]
    assert impl.event_type == "IMPLEMENTED"
    assert impl.event_date == date(2024, 3, 5) or impl.event_date == date(2024, 3, 3)


# ---------------------------------------------------------------------------
# Test 4: Rejection Extraction
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_04_rejection_extraction():
    content = """
    ADR-009: Apple Sign-In for Auth Module
    Status: REJECTED
    Date: March 20, 2024
    Decision makers: Priya Sharma, Legal Team

    Apple Sign-In is REJECTED.
    Legal review identified App Store guideline compliance requirements.
    """
    events = await extract_events_from_record(
        project_id="proj-p05",
        source_id="src-04",
        record_type="decision_log",
        title="ADR-009: Apple Sign-In",
        source_date=date(2024, 3, 20),
        source_date_raw="March 20, 2024",
        content=content,
    )
    rejected = [e for e in events if e.event_type == "REJECTED"]
    assert len(rejected) >= 1
    assert rejected[0].unresolved_feature_mention == "Apple Sign-In"
    assert "Priya Sharma" in (rejected[0].actor or "")


# ---------------------------------------------------------------------------
# Test 5: Rename Extraction (Rule E & Identity)
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_05_rename_extraction():
    content = """
    Notification Service to be renamed 'Comms Engine' to better reflect planned multi-channel support.
    """
    events = await extract_events_from_record(
        project_id="proj-p05",
        source_id="src-05",
        record_type="meeting_notes",
        title="Architecture Discussion",
        source_date=date(2024, 1, 10),
        source_date_raw="January 10, 2024",
        content=content,
    )
    renames = [e for e in events if e.event_type == "RENAMED"]
    assert len(renames) == 1
    assert renames[0].previous_name == "Notification Service"
    assert renames[0].new_name == "Comms Engine"


# ---------------------------------------------------------------------------
# Test 6: Removal / Deprecation Extraction
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_06_removal_deprecation_extraction():
    content = """
    Basic Search to be deprecated in Q2 2024.
    Hard removal date confirmed: April 30, 2024 (per ADR-007).
    """
    events = await extract_events_from_record(
        project_id="proj-p05",
        source_id="src-06",
        record_type="meeting_notes",
        title="Deprecation Notice",
        source_date=date(2024, 3, 15),
        source_date_raw="March 15, 2024",
        content=content,
    )
    removals = [e for e in events if e.event_type == "REMOVED"]
    assert len(removals) >= 1
    assert removals[0].unresolved_feature_mention == "Basic Search"


# ---------------------------------------------------------------------------
# Test 7: Dependency Addition Extraction
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_07_dependency_addition_extraction():
    content = """
    Feature: OAuth2 Social Login
    ## Dependencies
    - Dependencies: Auth Module v2.1
    """
    events = await extract_events_from_record(
        project_id="proj-p05",
        source_id="src-07",
        record_type="design_spec",
        title="OAuth2 Technical Specification",
        source_date=date(2024, 1, 22),
        source_date_raw="January 22, 2024",
        content=content,
    )
    deps = [e for e in events if e.event_type == "DEPENDENCY_ADDED"]
    assert len(deps) >= 1
    assert "Auth Module v2.1" in deps[0].description


# ---------------------------------------------------------------------------
# Test 8: Modification Extraction
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_08_modification_extraction():
    content = """
    Advanced Search v2:
    Frontend integration is in progress, estimated completion: March 28, 2024.
    Engineering effort estimate revised upward from 3 days to 3 weeks due to session complexity.
    """
    events = await extract_events_from_record(
        project_id="proj-p05",
        source_id="src-08",
        record_type="meeting_notes",
        title="Sprint Retrospective",
        source_date=date(2024, 3, 15),
        source_date_raw="March 15, 2024",
        content=content,
    )
    mods = [e for e in events if e.event_type == "MODIFIED"]
    assert len(mods) >= 1


# ---------------------------------------------------------------------------
# Test 9: Strict Date Separation (Rule C)
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_09_strict_date_separation_rule_c():
    content = """
    Dev Patel suggested adding CSV export functionality to reports.
    """
    # Record has NO date metadata
    events = await extract_events_from_record(
        project_id="proj-p05",
        source_id="src-09",
        record_type="meeting_notes",
        title="Undated Notes",
        source_date=None,
        source_date_raw=None,
        content=content,
    )
    assert len(events) >= 1
    ev = events[0]
    # Rule C: Never invent dates, never fallback to datetime.now()
    assert ev.event_date is None
    assert ev.event_date_precision == "unknown"
    assert ev.needs_review is True


# ---------------------------------------------------------------------------
# Test 10: Verbatim Evidence Compulsory (Rule H)
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_10_verbatim_evidence_compulsory_rule_h():
    content = """
    Priya proposed adding OAuth2 social login support to the existing Auth module.
    """
    events = await extract_events_from_record(
        project_id="proj-p05",
        source_id="src-10",
        record_type="meeting_notes",
        title="Meeting",
        source_date=date(2024, 1, 10),
        source_date_raw="January 10, 2024",
        content=content,
    )
    assert len(events) >= 1
    ev = events[0]
    # Rule H: Excerpt must be verbatim substring of content
    assert ev.evidence_excerpt.strip() in content


# ---------------------------------------------------------------------------
# Test 11: Zero Hallucination (Rule G)
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_11_zero_hallucination_rule_g():
    content = """
    A proposal was made to add WebSockets architecture.
    """
    events = await extract_events_from_record(
        project_id="proj-p05",
        source_id="src-11",
        record_type="meeting_notes",
        title="Architecture Discussion",
        source_date=date(2024, 2, 1),
        source_date_raw="February 1, 2024",
        content=content,
    )
    assert len(events) >= 1
    # Rule G: Actor is not mentioned, must be None, NOT hallucinated
    assert events[0].actor is None


# ---------------------------------------------------------------------------
# Test 12: Schema Invariant Enforcement (Model Validators)
# ---------------------------------------------------------------------------
def test_12_schema_validator_enforces_rules_a_and_b():
    # Rule A: IMPLEMENTED cannot have approval-only excerpt
    with pytest.raises(ValueError, match="Rule A violation"):
        TemporalEventCreate(
            project_id="proj-p05",
            event_type="IMPLEMENTED",
            description="Trying to mark as implemented",
            source_id="src-test",
            evidence_excerpt="No implementation has started yet — this is approval only.",
        )

    # Rule B: APPROVED cannot have unapproved proposal excerpt
    with pytest.raises(ValueError, match="Rule B violation"):
        TemporalEventCreate(
            project_id="proj-p05",
            event_type="APPROVED",
            description="Trying to mark as approved",
            source_id="src-test",
            evidence_excerpt="Dev suggested adding CSV export. No decision made. Pending design review.",
        )

    # Rule H: Compulsory non-empty evidence
    with pytest.raises(ValueError, match="Rule H violation"):
        TemporalEventCreate(
            project_id="proj-p05",
            event_type="PROPOSED",
            description="Missing evidence",
            source_id="src-test",
            evidence_excerpt="   ",
        )


# ---------------------------------------------------------------------------
# Test 13: Multi-Event Meeting Record Extraction
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_13_multi_event_meeting_record_extraction():
    content = """
    Attendees: Priya Sharma, Ravi Kumar, Ananya Nair, Dev Patel

    Agenda: Q1 roadmap discussion

    1. Authentication Module
       - Priya proposed adding OAuth2 social login support to the existing Auth module.
       - Decision: proposal accepted for Sprint 3 (starting Feb 5, 2024). Ravi Kumar assigned as owner.
       - Note: No implementation has started yet — this is approval only.

    2. Data Export Feature
       - Dev Patel suggested adding CSV export functionality to the dashboard reports section.
       - No decision made. Needs design review first.

    3. Notification Service
       - Existing email notification system to be renamed 'Comms Engine'.
       - Rename approved by team. Effective immediately in documentation.

    4. Search Module
       - Basic Search to be deprecated in Q2 2024.
       - Replacement: Advanced Search v2 using Elasticsearch.
    """
    events = await extract_events_from_record(
        project_id="proj-p05",
        source_id="src-multi",
        record_type="meeting_notes",
        title="Sprint Planning — Q1 2024",
        source_date=date(2024, 1, 10),
        source_date_raw="January 10, 2024",
        content=content,
    )
    # Must extract multiple distinct events
    types = {e.event_type for e in events}
    assert "PROPOSED" in types
    assert "APPROVED" in types
    assert "RENAMED" in types
    assert "REMOVED" in types

    # Rule A: No event from this meeting can be IMPLEMENTED
    assert "IMPLEMENTED" not in types


# ---------------------------------------------------------------------------
# Test 14: Evidence Offset Retention (Requirement F)
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_14_evidence_offset_retention():
    content = "Sprint Planning: Dev Patel suggested adding CSV export functionality to reports."
    events = await extract_events_from_record(
        project_id="proj-p05",
        source_id="src-14",
        record_type="meeting_notes",
        title="Sprint Planning",
        source_date=date(2024, 1, 10),
        source_date_raw="January 10, 2024",
        content=content,
    )
    assert len(events) >= 1
    ev = events[0]
    assert ev.evidence_offset_start is not None
    assert ev.evidence_offset_end is not None
    assert content[ev.evidence_offset_start:ev.evidence_offset_end] == ev.evidence_excerpt.strip()


# ---------------------------------------------------------------------------
# Test 15: Paraphrase Flagged as Needs Review (Requirement F)
# ---------------------------------------------------------------------------
def test_15_paraphrase_flagged_as_needs_review():
    content = "Team discussed adding CSV export."
    paraphrase = "The entire group agreed that exporting to CSV should be introduced immediately."
    is_verbatim, start, end = EventExtractor.verify_evidence(content, paraphrase)
    assert is_verbatim is False
    assert start is None
    assert end is None


# ---------------------------------------------------------------------------
# Test 16: Controlled 1-Shot Self-Correction (Requirement E)
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_16_controlled_1shot_self_correction():
    from app.services.llm_provider import BaseLLMProvider

    class MockSelfCorrectionProvider(BaseLLMProvider):
        def __init__(self):
            self.attempts = 0

        async def complete(self, system_prompt: str, user_prompt: str) -> str:
            return ""

        async def complete_json(self, system_prompt: str, user_prompt: str):
            self.attempts += 1
            if self.attempts == 1:
                # First attempt fails: invalid non-list payload
                raise ValueError("Unexpected JSON format: missing closing bracket")
            # Second attempt (correction) returns valid structured output
            return [
                {
                    "feature_mention": "OAuth2 Social Login",
                    "event_type": "APPROVED",
                    "description": "OAuth2 approved for sprint 3",
                    "previous_name": None,
                    "new_name": None,
                    "event_date_raw": "January 10, 2024",
                    "event_date_iso": "2024-01-10",
                    "event_date_precision": "exact",
                    "evidence_excerpt": "Decision: proposal accepted for Sprint 3",
                    "actor": "Ravi Kumar",
                    "extraction_confidence": 0.95,
                }
            ]

    mock_prov = MockSelfCorrectionProvider()
    extractor = EventExtractor(provider=mock_prov)
    content = "Sprint Notes: Decision: proposal accepted for Sprint 3"
    events = await extractor.extract_events(
        project_id="proj-p05",
        source_id="src-16",
        record_type="meeting_notes",
        title="Sprint Notes",
        source_date=date(2024, 1, 10),
        source_date_raw="January 10, 2024",
        content=content,
    )
    assert mock_prov.attempts == 2  # Exactly 1 initial + 1 correction attempt
    assert len(events) == 1
    assert events[0].event_type == "APPROVED"
    assert events[0].unresolved_feature_mention == "OAuth2 Social Login"


# ---------------------------------------------------------------------------
# Test 17: Contradictory Source Records Handling (Requirement G)
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_17_contradictory_source_records_discrete_preservation():
    # Source A approves the feature
    source_a = "Sprint 1: OAuth2 Social Login was approved by the architecture board."
    events_a = await extract_events_from_record(
        project_id="proj-p05",
        source_id="src-a",
        record_type="meeting_notes",
        title="Sprint 1",
        source_date=date(2024, 1, 10),
        source_date_raw="January 10, 2024",
        content=source_a,
    )
    # Source B rejects the feature due to security compliance
    source_b = "Security Audit: Status: REJECTED. OAuth2 Social Login was rejected by compliance."
    events_b = await extract_events_from_record(
        project_id="proj-p05",
        source_id="src-b",
        record_type="audit_report",
        title="Security Audit",
        source_date=date(2024, 1, 15),
        source_date_raw="January 15, 2024",
        content=source_b,
    )
    # Both events are preserved discretely with their respective source IDs without overwriting
    assert events_a[0].event_type == "APPROVED"
    assert events_a[0].source_id == "src-a"
    assert events_b[0].event_type == "REJECTED"
    assert events_b[0].source_id == "src-b"

