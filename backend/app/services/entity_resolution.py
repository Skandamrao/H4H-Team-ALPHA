"""
Entity Resolution Service.

Identifies when the same feature is referred to by different names
across different documents (e.g. "Google Login", "Google Auth", "OAuth Integration").

Approach:
  1. Normalise feature name strings.
  2. Apply fuzzy string matching (rapidfuzz).
  3. Flag potential duplicates above a similarity threshold.
  4. Maintain canonical names and alias lists.
  5. Never auto-merge features with similarity below MERGE_THRESHOLD.
     Matches between REVIEW_THRESHOLD and MERGE_THRESHOLD are flagged for review.
"""

import logging
import re
import unicodedata
from typing import List, Optional, Tuple

try:
    from rapidfuzz import fuzz, process
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False
    import difflib

from sqlalchemy.orm import Session

from app.models.models import Feature, FeatureAlias

logger = logging.getLogger(__name__)

# Similarity thresholds (0–100 scale used by rapidfuzz)
MERGE_THRESHOLD = 90    # Auto-merge — very high confidence the same feature
REVIEW_THRESHOLD = 72   # Flag for review — possible duplicate


def normalise_name(name: str) -> str:
    """
    Produce a clean, lowercase, punctuation-free representation of a feature name.

    'Google OAuth Integration' → 'google oauth integration'
    """
    # Unicode normalisation
    name = unicodedata.normalize("NFKC", name)
    # Lowercase
    name = name.lower()
    # Remove punctuation except spaces
    name = re.sub(r"[^\w\s]", " ", name)
    # Collapse whitespace
    name = re.sub(r"\s+", " ", name).strip()
    return name


def _get_all_feature_labels(db: Session) -> List[Tuple[str, str, str]]:
    """
    Return a list of (feature_id, canonical_name, normalised_canonical_name)
    for every feature in the database.
    """
    features = db.query(Feature).all()
    result = []
    for f in features:
        result.append((f.id, f.canonical_name, normalise_name(f.canonical_name)))
    # Also include aliases
    aliases = db.query(FeatureAlias).all()
    for a in aliases:
        result.append((a.feature_id, a.alias, normalise_name(a.alias)))
    return result


def find_matching_feature(
    db: Session,
    name: str,
    exclude_feature_id: Optional[str] = None,
) -> Tuple[Optional[Feature], float, str]:
    """
    Search the feature database for the best match to *name*.

    Returns (feature, similarity_score, match_status) where match_status is:
      'exact'   — normalised strings are identical
      'auto'    — similarity >= MERGE_THRESHOLD
      'review'  — similarity >= REVIEW_THRESHOLD
      'none'    — no match found
    """
    norm_input = normalise_name(name)
    labels = _get_all_feature_labels(db)

    if not labels:
        return None, 0.0, "none"

    # Build a mapping normalised_name → feature_id for the lookup
    norm_to_fid: dict[str, str] = {}
    for fid, _, norm in labels:
        if fid not in norm_to_fid:
            norm_to_fid[norm] = fid

    # Exact match (normalised)
    if norm_input in norm_to_fid:
        fid = norm_to_fid[norm_input]
        if fid == exclude_feature_id:
            return None, 100.0, "none"
        feature = db.get(Feature, fid)
        return feature, 100.0, "exact"

    # Fuzzy matching
    choices = list(norm_to_fid.keys())
    if HAS_RAPIDFUZZ:
        best = process.extractOne(norm_input, choices, scorer=fuzz.token_sort_ratio)
        if best is None:
            return None, 0.0, "none"
        best_norm, score, _ = best
    else:
        # Fallback using standard library difflib with token sorting
        best_norm = None
        score = 0.0
        norm_tokens = " ".join(sorted(norm_input.split()))
        for choice in choices:
            choice_tokens = " ".join(sorted(choice.split()))
            sim = difflib.SequenceMatcher(None, norm_tokens, choice_tokens).ratio() * 100
            if sim > score:
                score = sim
                best_norm = choice
        if best_norm is None or score <= 0.0:
            return None, 0.0, "none"
    fid = norm_to_fid[best_norm]

    if fid == exclude_feature_id:
        return None, score, "none"

    feature = db.get(Feature, fid)
    if feature is None:
        return None, score, "none"

    if score >= MERGE_THRESHOLD:
        return feature, score, "auto"
    elif score >= REVIEW_THRESHOLD:
        return feature, score, "review"
    return None, score, "none"


def ensure_feature_alias(db: Session, feature: Feature, alias: str, source_document_id: Optional[str]) -> None:
    """Add *alias* to *feature* if it does not already exist."""
    existing = (
        db.query(FeatureAlias)
        .filter(FeatureAlias.feature_id == feature.id, FeatureAlias.alias == alias)
        .first()
    )
    if existing is None:
        new_alias = FeatureAlias(
            feature_id=feature.id,
            alias=alias,
            source_document_id=source_document_id,
            is_canonical=(alias == feature.canonical_name),
        )
        db.add(new_alias)
        logger.info("Added alias '%s' to feature '%s'.", alias, feature.canonical_name)


def resolve_or_create_feature(
    db: Session,
    name: str,
    project_id: Optional[str],
    source_document_id: Optional[str],
) -> Tuple[Feature, bool]:
    """
    Resolve *name* to an existing Feature or create a new one.

    Returns (feature, was_created).
    """
    feature, score, status = find_matching_feature(db, name)

    if status in ("exact", "auto"):
        # Same feature — record alias if the name differs
        ensure_feature_alias(db, feature, name, source_document_id)
        logger.info("Resolved '%s' → existing feature '%s' (score=%.1f).", name, feature.canonical_name, score)
        return feature, False

    if status == "review":
        # Possible match — log for review but create a new feature to avoid incorrect merges
        logger.warning(
            "Possible duplicate: '%s' ≈ '%s' (score=%.1f) — creating separate feature for safety.",
            name, feature.canonical_name, score,
        )

    # Create a new feature
    new_feature = Feature(
        project_id=project_id,
        canonical_name=name,
        current_status="UNKNOWN",
    )
    db.add(new_feature)
    db.flush()  # Obtain the ID without committing

    # Record the canonical name as an alias
    canonical_alias = FeatureAlias(
        feature_id=new_feature.id,
        alias=name,
        source_document_id=source_document_id,
        is_canonical=True,
    )
    db.add(canonical_alias)
    logger.info("Created new feature '%s'.", name)
    return new_feature, True

