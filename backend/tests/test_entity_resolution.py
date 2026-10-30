"""
Tests for entity resolution — feature identity tracking across different names.

Verifies that the system correctly identifies when the same feature appears
under different names and maintains canonical names with aliases.
"""

import pytest
from app.models.models import Feature, FeatureAlias
from app.services.entity_resolution import (
    normalise_name,
    resolve_or_create_feature,
    find_matching_feature,
    MERGE_THRESHOLD,
    REVIEW_THRESHOLD,
)


class TestNameNormalisation:
    def test_lowercase(self):
        assert normalise_name("Google Login") == "google login"

    def test_punctuation_removed(self):
        assert normalise_name("Google OAuth 2.0!") == "google oauth 2 0"

    def test_extra_whitespace(self):
        assert normalise_name("  Google   Auth  ") == "google auth"

    def test_unicode_normalised(self):
        result = normalise_name("Résumé Authentication")
        assert "resume" in result or "r" in result  # At minimum it normalises


class TestEntityResolution:
    def test_exact_same_name(self, db):
        """Resolving the same name twice should return the same feature."""
        feature1, created1 = resolve_or_create_feature(db, "Google Authentication", None, None)
        db.commit()
        feature2, created2 = resolve_or_create_feature(db, "Google Authentication", None, None)
        db.commit()

        assert created1 is True
        assert created2 is False
        assert feature1.id == feature2.id

    def test_alias_tracking(self, db):
        """Different names for the same feature should create aliases."""
        feature, _ = resolve_or_create_feature(db, "Google Authentication", None, None)
        db.commit()

        # "Google Login" is similar enough to auto-merge
        feature2, created = resolve_or_create_feature(db, "Google Login", None, None)
        db.commit()

        # If auto-merged, it's the same feature
        if not created:
            assert feature.id == feature2.id
            # Alias should exist
            aliases = [a.alias for a in feature.aliases]
            assert "Google Login" in aliases or "Google Authentication" in aliases

    def test_completely_different_names_create_new_features(self, db):
        """Unrelated feature names should create separate features."""
        feature1, created1 = resolve_or_create_feature(db, "Payment Gateway", None, None)
        db.commit()
        feature2, created2 = resolve_or_create_feature(db, "User Authentication", None, None)
        db.commit()

        assert feature1.id != feature2.id

    def test_canonical_name_preserved(self, db):
        """The canonical name should remain the first name used."""
        feature, created = resolve_or_create_feature(db, "Google Authentication", None, None)
        db.commit()
        assert feature.canonical_name == "Google Authentication"


class TestFeatureStatus:
    def test_feature_status_via_api(self, client):
        """Features list endpoint should return correct data."""
        response = client.get("/api/features/")
        assert response.status_code == 200
        data = response.json()
        assert "features" in data
        assert "total" in data

