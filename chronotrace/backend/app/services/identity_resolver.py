"""
ChronoTrace AI — Feature Identity Resolver
Resolves feature mentions to canonical Feature entities.

Rule E: Similarity alone NEVER creates an automatic identity merge.
         Only explicit alias evidence (e.g. "formerly known as", rename events) does.
"""
from __future__ import annotations

import logging
import re
import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import Feature, FeatureAlias

def _uuid() -> str:
    return str(uuid.uuid4())

logger = logging.getLogger(__name__)


def _normalise(name: str) -> str:
    """Lower-case, replace punctuation with spaces, collapse whitespace for comparison."""
    # Replace non-alphanumeric chars with space so "Auth-Module" becomes "auth module"
    cleaned = re.sub(r"[^\w\s]", " ", name.lower())
    return " ".join(cleaned.split())


async def resolve_feature_mention(
    db: AsyncSession,
    project_id: str,
    mention: str,
    source_id: str,
    evidence_excerpt: str,
    allow_new: bool = True,
) -> Optional[str]:
    """
    Attempt to resolve a feature mention string to an existing Feature.id.

    Matching strategy (in priority order):
      1. Exact canonical_name match (case-insensitive, normalised).
      2. Existing alias match.

    If no match: creates a new Feature only if allow_new=True.

    Does NOT merge by similarity (Rule E).
    Returns the feature ID or None.
    """
    if not mention or not mention.strip():
        return None

    norm = _normalise(mention)

    # ── 1. Check canonical names ──────────────────────────────────────────────
    result = await db.execute(
        select(Feature).where(Feature.project_id == project_id)
    )
    features = result.scalars().all()

    for feat in features:
        if _normalise(feat.canonical_name) == norm:
            # Ensure the mention is recorded as an alias if different in form
            await _ensure_alias(db, feat.id, mention, source_id, evidence_excerpt)
            return feat.id

    # ── 2. Check aliases ──────────────────────────────────────────────────────
    alias_result = await db.execute(
        select(FeatureAlias).join(Feature).where(Feature.project_id == project_id)
    )
    aliases = alias_result.scalars().all()

    for alias in aliases:
        if _normalise(alias.alias) == norm:
            return alias.feature_id

    # ── 3. No match — create new feature (if allowed) ────────────────────────
    if not allow_new:
        return None

    new_feature = Feature(
        id=_uuid(),
        project_id=project_id,
        canonical_name=mention.strip(),
    )
    db.add(new_feature)
    await db.flush()  # get the ID without committing

    # Record the original mention as the first alias
    await _ensure_alias(db, new_feature.id, mention, source_id, evidence_excerpt)

    logger.info("Created new feature '%s' (id=%s)", mention, new_feature.id)
    return new_feature.id


async def _ensure_alias(
    db: AsyncSession,
    feature_id: str,
    alias_text: str,
    source_id: str,
    evidence_excerpt: str,
) -> None:
    """Add an alias if it doesn't already exist (idempotent)."""
    existing = await db.execute(
        select(FeatureAlias).where(
            FeatureAlias.feature_id == feature_id,
            FeatureAlias.alias == alias_text.strip(),
        )
    )
    if existing.scalars().first() is None:
        db.add(FeatureAlias(
            id=_uuid(),
            feature_id=feature_id,
            alias=alias_text.strip(),
            source_id=source_id,
            evidence_excerpt=evidence_excerpt[:512],
        ))


async def apply_rename(
    db: AsyncSession,
    feature_id: str,
    new_name: str,
    source_id: str,
    evidence_excerpt: str,
) -> None:
    """
    Record a rename: update canonical_name and add the old name as an alias.
    Called ONLY when processing a RENAMED event (explicit evidence — Rule E).
    """
    result = await db.execute(select(Feature).where(Feature.id == feature_id))
    feature = result.scalars().first()
    if not feature:
        return

    old_name = feature.canonical_name
    # Preserve old name as alias
    await _ensure_alias(db, feature_id, old_name, source_id, evidence_excerpt)
    # Update canonical (this is a metadata update on the Feature row, not a TemporalEvent row)
    feature.canonical_name = new_name.strip()
    await _ensure_alias(db, feature_id, new_name, source_id, evidence_excerpt)

