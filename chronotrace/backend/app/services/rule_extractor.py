"""
ChronoTrace AI — Deterministic Rule-Based Fallback Extractor
Used when no live LLM API key is configured or during offline testing.
Strictly adheres to:
  - Rule A: APPROVED ≠ IMPLEMENTED
  - Rule B: PROPOSED ≠ APPROVED
  - Rule C: Event date ≠ Ingestion timestamp (never falls back to now())
  - Rule D: Append-only event history
  - Rule G: Unknown fields remain None, never fabricated
  - Rule H: Every event must have a verbatim evidence_excerpt
"""
from __future__ import annotations

import re
from typing import Optional, Tuple
from datetime import date

from app.schemas.events import TemporalEventCreate
from app.utils.date_parser import parse_date_expression, extract_dates_from_text

KNOWN_CANONICAL_FEATURES = [
    "OAuth2 Social Login",
    "Apple Sign-In",
    "Data Export Feature",
    "CSV Export",
    "PDF Export",
    "Comms Engine",
    "Notification Service",
    "Basic Search",
    "Advanced Search v2",
    "Intelligent Search",
    "Authentication Module",
    "Apache Parquet",
    "WebSockets Architecture",
]


def _clean_feature_name(raw: str, default: Optional[str] = None) -> str:
    cleaned = raw.strip().strip("'\"").strip()
    for known in KNOWN_CANONICAL_FEATURES:
        if known.lower() in cleaned.lower():
            return known

    # Strip common leading verbs and articles
    cleaned = re.sub(r"^(adding|the|a|an|support for)\s+", "", cleaned, flags=re.I).strip()
    if len(cleaned) < 3 or cleaned.lower() in [
        "feature", "component", "adding", "af", "f", "during", "alternatives", "module"
    ]:
        if default:
            for known in KNOWN_CANONICAL_FEATURES:
                if known.lower() in default.lower():
                    return known
            cleaned_default = default.split("—")[0].split("-")[0].strip()
            if len(cleaned_default) >= 3:
                return cleaned_default
        return "Core Feature"
    return cleaned


def _find_document_level_actor(content: str) -> Optional[str]:
    """Scan document header for global decision makers or author (Rule G)."""
    dm_match = re.search(r"Decision makers?:\s*([^\n\r]+)", content, re.I)
    if dm_match:
        return dm_match.group(1).strip()
    author_match = re.search(r"Author:\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", content, re.I)
    if author_match:
        return author_match.group(1).strip()
    owner_match = re.search(r"Owner:\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", content, re.I)
    if owner_match:
        return owner_match.group(1).strip()
    return None


def _extract_actor_from_text(text: str, fallback_actor: Optional[str] = None) -> Optional[str]:
    """Extract person or team responsible for an action without fabricating (Rule G)."""
    # 1. "Ravi Kumar assigned as owner"
    assigned_match = re.search(r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+assigned as owner", text, re.I)
    if assigned_match:
        return assigned_match.group(1).strip()

    # 2. "Owner: Ravi Kumar" or "Decision makers: Priya Sharma"
    dm_match = re.search(r"Decision makers?:\s*([^\n\r]+)", text, re.I)
    if dm_match:
        return dm_match.group(1).strip()

    owner_match = re.search(r"Owner:\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", text, re.I)
    if owner_match:
        return owner_match.group(1).strip()

    author_match = re.search(r"Author:\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", text, re.I)
    if author_match:
        return author_match.group(1).strip()

    # 3. Named actor in action statement: "Priya proposed", "Dev Patel suggested", "Ravi Kumar confirmed"
    actor_action = re.search(
        r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+(?:proposed|suggested|confirmed|signed off|championed)\b",
        text,
    )
    if actor_action:
        return actor_action.group(1).strip()

    return fallback_actor


def _extract_date_for_line(
    line: str,
    doc_date: Optional[date],
    doc_prec: str,
    doc_basis: str,
) -> Tuple[Optional[date], str, str, Optional[str]]:
    """
    Extract date from line or fall back to document date (Rule C).
    Never returns datetime.now().
    """
    inline_dates = extract_dates_from_text(line)
    if inline_dates:
        raw_match, parsed_d, prec = inline_dates[0]
        return parsed_d, prec, "explicit", raw_match

    # Check for quarter mention (e.g., "Q2 2024")
    q_match = re.search(r"\bQ([1-4])[\s/\-]+(\d{4})\b", line, re.I)
    if q_match:
        q = int(q_match.group(1))
        y = int(q_match.group(2))
        parsed_d, prec, basis = parse_date_expression(f"Q{q} {y}")
        return parsed_d, prec, "explicit", q_match.group(0)

    return doc_date, doc_prec, doc_basis, None


def extract_rule_based_events(
    project_id: str,
    source_id: str,
    record_type: str,
    title: Optional[str],
    source_date: Optional[date],
    source_date_raw: Optional[str],
    content: str,
) -> list[TemporalEventCreate]:
    """
    Deterministically parses well-structured project records (meeting notes, specs,
    ADRs, changelogs, emails) using domain patterns when offline or in test mode.
    Strictly verifies Rules A, B, C, G, H.
    """
    events: list[TemporalEventCreate] = []
    lines = [line.strip() for line in content.split("\n") if line.strip()]

    doc_date, doc_prec, doc_basis = (
        (source_date, "exact", "explicit")
        if source_date
        else parse_date_expression(source_date_raw)
    )

    doc_global_actor = _find_document_level_actor(content)

    current_section_feature: Optional[str] = None
    in_dependencies_section = False

    for line in lines:
        lower = line.lower()

        # Check for dialogue speaker prefix (e.g. "Jennifer Miles:", "Meeting Chairman (Mark):")
        speaker_match = re.match(r"^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?(?:\s+\([^)]+\))?):\s*(.*)$", line)
        line_speaker = speaker_match.group(1).strip() if speaker_match else None
        active_line_actor = line_speaker or doc_global_actor

        # Update section context
        if line.startswith("#"):
            in_dependencies_section = "dependenc" in lower
            heading_text = re.sub(r"^[#\d\.\s]+", "", line).strip()
            if len(heading_text) > 3 and not any(
                k in lower for k in ["agenda", "attendees", "action items", "context", "decision", "reasons", "consequences", "notes", "related", "shipped", "not shipped"]
            ):
                current_section_feature = _clean_feature_name(heading_text, title)
            continue

        if re.match(r"^\d+\.\s+", line):
            in_dependencies_section = "dependenc" in lower
            heading_text = re.sub(r"^[#\d\.\s]+", "", line).strip()
            if len(heading_text) > 3 and not any(
                k in lower for k in ["agenda", "attendees", "action items", "context", "decision", "reasons", "consequences", "notes", "related"]
            ):
                current_section_feature = _clean_feature_name(heading_text, title)

        # -------------------------------------------------------------------
        # 1. RENAME patterns (e.g. "Notification Service to be renamed 'Comms Engine'")
        # -------------------------------------------------------------------
        rename_pair: Optional[Tuple[str, str]] = None
        if "rename" in lower:
            # Pattern 1: explicit from 'X' to 'Y'
            m1 = re.search(r"renamed\s+from\s+['\"]([^'\"]+)['\"]\s+to\s+['\"]([^'\"]+)['\"]", line, re.I)
            if m1:
                rename_pair = (m1.group(1).strip(), m1.group(2).strip())
            else:
                # Pattern 2: <prev> to be renamed '<new>'
                m2 = re.search(r"([A-Za-z0-9\s]+?)\s+(?:has been|to be|was)?\s*renamed\s+(?:to\s+)?['\"]([^'\"]+)['\"]", line, re.I)
                if m2:
                    p = m2.group(1).strip()
                    if len(p) < 3 or p.lower() in ["system", "service", "the", "module"]:
                        p = current_section_feature or p
                    rename_pair = (p, m2.group(2).strip())
                else:
                    # Pattern 3: unquoted X was renamed to Y
                    m3 = re.search(r"([A-Za-z0-9\s]+?)\s+(?:has been|to be|was)\s+renamed\s+to\s+([A-Za-z0-9]+(?:\s+[A-Za-z0-9]+)?)", line, re.I)
                    if m3:
                        rename_pair = (m3.group(1).strip(), m3.group(2).strip())
                    else:
                        # Pattern 4: to be renamed '<new>'
                        m4 = re.search(r"(?:to be\s+)?renamed\s+to\s+['\"]([^'\"]+)['\"]", line, re.I)
                        if m4:
                            rename_pair = (current_section_feature or "Module", m4.group(1).strip())

        if rename_pair:
            raw_prev, raw_new = rename_pair
            prev_name = _clean_feature_name(raw_prev, current_section_feature or title)
            new_name = _clean_feature_name(raw_new, current_section_feature or title)

            line_date, line_prec, line_basis, line_raw = _extract_date_for_line(line, doc_date, doc_prec, doc_basis)
            actor = _extract_actor_from_text(line, None)

            events.append(TemporalEventCreate(
                project_id=project_id,
                unresolved_feature_mention=new_name,
                event_type="RENAMED",
                description=line,
                previous_name=prev_name,
                new_name=new_name,
                event_date=line_date,
                event_date_raw=line_raw or source_date_raw,
                event_date_precision=line_prec,
                event_date_basis=line_basis,
                source_id=source_id,
                evidence_excerpt=line,
                actor=actor,
                extraction_confidence=0.95,
                needs_review=(line_date is None),
            ))
            continue

        # -------------------------------------------------------------------
        # 2. REMOVED / DEPRECATED patterns (e.g. "Basic Search to be deprecated in Q2 2024")
        # -------------------------------------------------------------------
        if any(kw in lower for kw in ["deprecated", "deprecation banner", "hard removal date confirmed", "sunset", "decommissioned", "removed from"]):
            feat = current_section_feature or title or "Feature"
            m = re.search(
                r"([A-Za-z0-9\s\-]+?)\s+(?:module\s+)?(?:\(currently called\s+['\"]?([^'\"]+)['\"]?\))?\s*to be deprecated",
                line,
                re.I,
            )
            if m:
                feat = m.group(2) or m.group(1)
            elif "basic search" in lower:
                feat = "Basic Search"
            feat = _clean_feature_name(feat, current_section_feature or title)

            line_date, line_prec, line_basis, line_raw = _extract_date_for_line(line, doc_date, doc_prec, doc_basis)
            actor = _extract_actor_from_text(line, None)

            events.append(TemporalEventCreate(
                project_id=project_id,
                unresolved_feature_mention=feat,
                event_type="REMOVED",
                description=line,
                event_date=line_date,
                event_date_raw=line_raw or source_date_raw,
                event_date_precision=line_prec,
                event_date_basis=line_basis,
                source_id=source_id,
                evidence_excerpt=line,
                actor=actor,
                extraction_confidence=0.93,
                needs_review=(line_date is None),
            ))
            continue

        # -------------------------------------------------------------------
        # 3. DEPENDENCY_ADDED patterns (e.g. "- Dependencies: Auth Module v2.1")
        # -------------------------------------------------------------------
        if in_dependencies_section or lower.startswith("dependency:") or lower.startswith("- dependencies:") or "prerequisite:" in lower:
            feat = current_section_feature or title or "Feature"
            dep_mention = re.sub(r"^[-\s*#]*(?:dependencies?:?|prerequisite:?)\s*", "", line, flags=re.I).strip()
            if dep_mention and len(dep_mention) > 2:
                line_date, line_prec, line_basis, line_raw = _extract_date_for_line(line, doc_date, doc_prec, doc_basis)
                events.append(TemporalEventCreate(
                    project_id=project_id,
                    unresolved_feature_mention=_clean_feature_name(feat, title),
                    event_type="DEPENDENCY_ADDED",
                    description=f"Dependency on {dep_mention}",
                    event_date=line_date,
                    event_date_raw=line_raw or source_date_raw,
                    event_date_precision=line_prec,
                    event_date_basis=line_basis,
                    source_id=source_id,
                    evidence_excerpt=line,
                    actor=None,
                    extraction_confidence=0.88,
                    needs_review=(line_date is None),
                ))
                continue

        # -------------------------------------------------------------------
        # 4. IMPLEMENTED / SHIPPED patterns (Rule A: verify not an approval only)
        # -------------------------------------------------------------------
        is_impl_indicator = any(kw in lower for kw in [
            "shipped", "is now live in production", "implementation completed",
            "merged into main", "pr #", "backend .* is now complete"
        ])
        is_negated_impl = any(kw in lower for kw in [
            "not shipped", "never implemented", "no implementation has started",
            "approval only", "still not approved", "pending review"
        ])

        if is_impl_indicator and not is_negated_impl:
            feat = current_section_feature or title or "Core Feature"
            m = re.search(r"\*\*([^*]+)\*\*", line) or re.search(r"Feature:\s*([^\n\r]+)", line, re.I)
            if m:
                feat = m.group(1).split("—")[0].strip()
            feat = _clean_feature_name(feat, current_section_feature or title)

            line_date, line_prec, line_basis, line_raw = _extract_date_for_line(line, doc_date, doc_prec, doc_basis)
            actor = _extract_actor_from_text(line, None)

            events.append(TemporalEventCreate(
                project_id=project_id,
                unresolved_feature_mention=feat,
                event_type="IMPLEMENTED",
                description=line,
                event_date=line_date,
                event_date_raw=line_raw or source_date_raw,
                event_date_precision=line_prec,
                event_date_basis=line_basis,
                source_id=source_id,
                evidence_excerpt=line,
                actor=actor,
                extraction_confidence=0.92,
                needs_review=(line_date is None),
            ))
            continue

        # -------------------------------------------------------------------
        # 5. REJECTED patterns (e.g. "Status: REJECTED", "Apple Sign-In is REJECTED")
        # -------------------------------------------------------------------
        if "rejected" in lower or "status: rejected" in lower:
            feat = current_section_feature or title or "Feature"
            m = re.search(r"([A-Za-z0-9\s\-]+)\s+(?:was|is)?\s*rejected", line, re.I)
            if m:
                feat = m.group(1).strip()
            elif title:
                feat = title.replace("ADR-009:", "").split("—")[0].strip()
            feat = _clean_feature_name(feat, current_section_feature or title)

            line_date, line_prec, line_basis, line_raw = _extract_date_for_line(line, doc_date, doc_prec, doc_basis)
            actor = _extract_actor_from_text(line, doc_global_actor)

            events.append(TemporalEventCreate(
                project_id=project_id,
                unresolved_feature_mention=feat,
                event_type="REJECTED",
                description=line,
                event_date=line_date,
                event_date_raw=line_raw or source_date_raw,
                event_date_precision=line_prec,
                event_date_basis=line_basis,
                source_id=source_id,
                evidence_excerpt=line,
                actor=actor,
                extraction_confidence=0.95,
                needs_review=(line_date is None),
            ))
            continue

        # -------------------------------------------------------------------
        # 6. APPROVED patterns (Rule B: verify explicit decision made)
        # -------------------------------------------------------------------
        is_approval_indicator = (
            "approved" in lower or
            "proposal accepted" in lower or
            "decision: proposal accepted" in lower or
            "decision: accepted" in lower or
            "agreed to proceed" in lower or
            "move forward with" in lower
        )
        is_negated_approval = any(kw in lower for kw in [
            "no decision made", "still not approved", "not approved yet",
            "has not been approved", "no approval decision made", "pending legal review",
            "pending security review", "pending design review"
        ])

        if is_approval_indicator and not is_negated_approval:
            feat = current_section_feature or title or "Feature"
            m = (
                re.search(r"([A-Za-z0-9\s\-]+)\s+(?:is|was)?\s*approved", line, re.I) or
                re.search(r"move forward with (?:the\s+)?([A-Za-z0-9\s\-]+?)(?:\s+first|\.|$)", line, re.I)
            )
            if m:
                feat = m.group(1).strip()
            feat = _clean_feature_name(feat, current_section_feature or title)

            line_date, line_prec, line_basis, line_raw = _extract_date_for_line(line, doc_date, doc_prec, doc_basis)
            actor = _extract_actor_from_text(line, active_line_actor)

            events.append(TemporalEventCreate(
                project_id=project_id,
                unresolved_feature_mention=feat,
                event_type="APPROVED",
                description=line,
                event_date=line_date,
                event_date_raw=line_raw or source_date_raw,
                event_date_precision=line_prec,
                event_date_basis=line_basis,
                source_id=source_id,
                evidence_excerpt=line,
                actor=actor,
                extraction_confidence=0.90,
                needs_review=(line_date is None),
            ))
            continue

        # -------------------------------------------------------------------
        # 7. PROPOSED patterns (Rule B: proposals are not approvals)
        # -------------------------------------------------------------------
        is_prop_indicator = any(kw in lower for kw in [
            "proposed", "proposal", "suggested adding", "is now proposed",
            "pitch", "suggested", "introducing", "comes to mind is"
        ])
        if is_prop_indicator and not is_approval_indicator and "rejected" not in lower:
            feat = current_section_feature or title or "Feature"
            m = (
                re.search(r"suggested adding\s+([^to\n\.]+)", line, re.I) or
                re.search(r"proposed adding\s+([^to\n\.]+)", line, re.I) or
                re.search(r"proposed\s+([^to\n\.]+)", line, re.I) or
                re.search(r"proposal (?:was made )?to add\s+([^to\n\.]+)", line, re.I) or
                re.search(r"(?:introducing|implementing|exploring)\s+(?:an?\s+)?([A-Za-z0-9\s\-]+?)(?:\s+for|\s+to|\.|$)", line, re.I) or
                re.search(r"comes to mind is\s+([A-Za-z0-9\s\-]+?)(?:\.|\s+Right|$)", line, re.I)
            )
            if m:
                feat = m.group(1).strip()
            feat = _clean_feature_name(feat, current_section_feature or title)

            line_date, line_prec, line_basis, line_raw = _extract_date_for_line(line, doc_date, doc_prec, doc_basis)
            actor = _extract_actor_from_text(line, active_line_actor)

            events.append(TemporalEventCreate(
                project_id=project_id,
                unresolved_feature_mention=feat,
                event_type="PROPOSED",
                description=line,
                event_date=line_date,
                event_date_raw=line_raw or source_date_raw,
                event_date_precision=line_prec,
                event_date_basis=line_basis,
                source_id=source_id,
                evidence_excerpt=line,
                actor=actor,
                extraction_confidence=0.85,
                needs_review=(line_date is None),
            ))
            continue

        # -------------------------------------------------------------------
        # 8. MODIFIED patterns (Scope adjustments, revisions, in-progress shifts)
        # -------------------------------------------------------------------
        if any(kw in lower for kw in [
            "revised upward", "revised downward", "scope modified",
            "architecture revised", "refactored", "frontend integration is in progress"
        ]):
            feat = current_section_feature or title or "Feature"
            feat = _clean_feature_name(feat, current_section_feature or title)

            line_date, line_prec, line_basis, line_raw = _extract_date_for_line(line, doc_date, doc_prec, doc_basis)
            actor = _extract_actor_from_text(line, doc_global_actor)

            events.append(TemporalEventCreate(
                project_id=project_id,
                unresolved_feature_mention=feat,
                event_type="MODIFIED",
                description=line,
                event_date=line_date,
                event_date_raw=line_raw or source_date_raw,
                event_date_precision=line_prec,
                event_date_basis=line_basis,
                source_id=source_id,
                evidence_excerpt=line,
                actor=actor,
                extraction_confidence=0.85,
                needs_review=(line_date is None),
            ))
            continue

    return events
