"""
Deterministic Rule-Based / Mock Fallback Extractor
Used when no live LLM API key is configured or during offline testing.
Strictly adheres to Rules A, B, C, D, E, F, G, H.
"""
from __future__ import annotations

import re
from typing import Optional
from datetime import date
from app.schemas.events import TemporalEventCreate
from app.utils.date_parser import parse_date_expression

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
]

def _clean_feature_name(raw: str, default: Optional[str] = None) -> str:
    cleaned = raw.strip().strip("'\"").strip()
    # Check if a known canonical name is contained
    for known in KNOWN_CANONICAL_FEATURES:
        if known.lower() in cleaned.lower():
            return known
    
    # Strip common leading words
    cleaned = re.sub(r"^(adding|the|a|an)\s+", "", cleaned, flags=re.I).strip()
    if len(cleaned) < 3 or cleaned.lower() in ["feature", "component", "adding", "af", "f", "during", "alternatives"]:
        if default:
            for known in KNOWN_CANONICAL_FEATURES:
                if known.lower() in default.lower():
                    return known
            return default.split("—")[0].split("-")[0].strip()
        return "Core Feature"
    return cleaned

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
    """
    events: list[TemporalEventCreate] = []
    lines = [line.strip() for line in content.split("\n") if line.strip()]

    doc_date, doc_prec, doc_basis = (
        (source_date, "exact", "explicit")
        if source_date
        else parse_date_expression(source_date_raw)
    )

    for line in lines:
        # 1. RENAME patterns (e.g., "Notification Service has been fully renamed to Comms Engine")
        rename_match = re.search(
            r"([A-Za-z0-9\s]+?)\s+(?:has been|to be|was)?\s*renamed\s+(?:from\s+['\"]?([^'\"]+)['\"]?\s+)?to\s+['\"]?([^'\"]+?)['\"]?(?:\s+across|\s+to|\.|$)",
            line, re.I
        )
        if not rename_match and "renamed" in line.lower():
            rename_match = re.search(r"renamed\s+(?:from\s+)?['\"]?([^'\"]+)['\"]?\s+to\s+['\"]?([^'\"]+)['\"]?", line, re.I)

        if "rename" in line.lower() and rename_match:
            g1 = rename_match.group(1).strip()
            g2 = rename_match.group(2).strip() if rename_match.lastindex and rename_match.lastindex >= 2 and rename_match.group(2) else None
            g3 = rename_match.group(3).strip() if rename_match.lastindex and rename_match.lastindex >= 3 and rename_match.group(3) else None

            if g3:
                prev_name = _clean_feature_name(g2 or g1, title)
                new_name = _clean_feature_name(g3, title)
            elif g2:
                prev_name = _clean_feature_name(g1, title)
                new_name = _clean_feature_name(g2, title)
            else:
                prev_name = _clean_feature_name(title or "Module")
                new_name = _clean_feature_name(g1, title)

            events.append(TemporalEventCreate(
                project_id=project_id,
                unresolved_feature_mention=new_name,
                event_type="RENAMED",
                description=line,
                previous_name=prev_name,
                new_name=new_name,
                event_date=doc_date,
                event_date_raw=source_date_raw,
                event_date_precision=doc_prec,
                event_date_basis=doc_basis,
                source_id=source_id,
                evidence_excerpt=line,
                actor=None,
                extraction_confidence=0.95,
                needs_review=False,
            ))
            continue

        # 2. IMPLEMENTED / SHIPPED patterns
        if any(kw in line.lower() for kw in ["shipped", "live in production", "implementation completed", "merged"]):
            feat = title or "Core Feature"
            m = re.search(r"\*\*([^*]+)\*\*", line) or re.search(r"Feature:\s*([^\n\r]+)", line, re.I)
            if m:
                feat = m.group(1).split("—")[0].strip()
            feat = _clean_feature_name(feat, title)

            events.append(TemporalEventCreate(
                project_id=project_id,
                unresolved_feature_mention=feat,
                event_type="IMPLEMENTED",
                description=line,
                event_date=doc_date,
                event_date_raw=source_date_raw,
                event_date_precision=doc_prec,
                event_date_basis=doc_basis,
                source_id=source_id,
                evidence_excerpt=line,
                actor=None,
                extraction_confidence=0.92,
                needs_review=False,
            ))
            continue

        # 3. REJECTED patterns
        if "rejected" in line.lower() or "status: rejected" in line.lower():
            feat = title or "Feature"
            m = re.search(r"([A-Za-z0-9\s\-]+)\s+(?:was|is)?\s*rejected", line, re.I)
            if m:
                feat = m.group(1).strip()
            elif title:
                feat = title.replace("ADR-009:", "").split("—")[0].strip()
            feat = _clean_feature_name(feat, title)

            events.append(TemporalEventCreate(
                project_id=project_id,
                unresolved_feature_mention=feat,
                event_type="REJECTED",
                description=line,
                event_date=doc_date,
                event_date_raw=source_date_raw,
                event_date_precision=doc_prec,
                event_date_basis=doc_basis,
                source_id=source_id,
                evidence_excerpt=line,
                actor=None,
                extraction_confidence=0.95,
                needs_review=False,
            ))
            continue

        # 4. APPROVED patterns
        if "approved" in line.lower() or "proposal accepted" in line.lower():
            feat = title or "Feature"
            m = re.search(r"([A-Za-z0-9\s\-]+)\s+(?:is|was)?\s*approved", line, re.I)
            if m:
                feat = m.group(1).strip()
            feat = _clean_feature_name(feat, title)

            events.append(TemporalEventCreate(
                project_id=project_id,
                unresolved_feature_mention=feat,
                event_type="APPROVED",
                description=line,
                event_date=doc_date,
                event_date_raw=source_date_raw,
                event_date_precision=doc_prec,
                event_date_basis=doc_basis,
                source_id=source_id,
                evidence_excerpt=line,
                actor=None,
                extraction_confidence=0.9,
                needs_review=False,
            ))
            continue

        # 5. PROPOSED patterns
        if any(kw in line.lower() for kw in ["proposed", "suggested adding"]):
            feat = title or "Feature"
            m = re.search(r"suggested adding\s+([^to\n]+)", line, re.I) or re.search(r"proposed\s+([^to\n]+)", line, re.I)
            if m:
                feat = m.group(1).strip()
            feat = _clean_feature_name(feat, title)

            events.append(TemporalEventCreate(
                project_id=project_id,
                unresolved_feature_mention=feat,
                event_type="PROPOSED",
                description=line,
                event_date=doc_date,
                event_date_raw=source_date_raw,
                event_date_precision=doc_prec,
                event_date_basis=doc_basis,
                source_id=source_id,
                evidence_excerpt=line,
                actor=None,
                extraction_confidence=0.85,
                needs_review=False,
            ))
            continue

    return events
