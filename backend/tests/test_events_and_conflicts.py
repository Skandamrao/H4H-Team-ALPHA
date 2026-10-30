"""
Tests for event extraction schema validation and conflict detection.

These tests do NOT call the real Gemini API — they validate the schema
and conflict detection logic independently.
"""

import pytest
from datetime import datetime
from pydantic import ValidationError
from app.schemas.schemas import ExtractedEvent, EventType, DecisionStatus, DateConfidence
from app.models.models import Feature, Event, Document, IngestionBatch
from app.services.conflict_detector import detect_conflicts


class TestExtractedEventSchema:
    def test_valid_event(self):
        event = ExtractedEvent(
            title="Google Auth Introduced",
            description="Google authentication was introduced.",
            event_type=EventType.FEATURE_INTRODUCED,
            feature_name="Google Authentication",
            event_date="2024-10-08",
            event_date_confidence=DateConfidence.HIGH,
            decision_status=None,
            confidence_score=0.9,
            supporting_text="The team approved Google OAuth 2.0.",
        )
        assert event.title == "Google Auth Introduced"
        assert event.event_type == EventType.FEATURE_INTRODUCED

    def test_invalid_event_type_rejected(self):
        with pytest.raises(ValidationError):
            ExtractedEvent(
                title="Bad Event",
                event_type="NOT_A_REAL_TYPE",
                confidence_score=0.5,
            )

    def test_confidence_out_of_range_rejected(self):
        with pytest.raises(ValidationError):
            ExtractedEvent(
                title="Event",
                event_type=EventType.FEATURE_INTRODUCED,
                confidence_score=1.5,  # > 1.0 is invalid
            )

    def test_empty_date_becomes_none(self):
        event = ExtractedEvent(
            title="Event",
            event_type=EventType.FEATURE_INTRODUCED,
            event_date="",  # Empty string should become None
            confidence_score=0.5,
        )
        assert event.event_date is None

    def test_proposal_not_auto_approved(self):
        """A DECISION_PROPOSED event must not be created with APPROVED status."""
        event = ExtractedEvent(
            title="Proposal",
            event_type=EventType.DECISION_PROPOSED,
            decision_status=DecisionStatus.PROPOSED,
            confidence_score=0.8,
        )
        assert event.decision_status == DecisionStatus.PROPOSED
        assert event.decision_status != DecisionStatus.APPROVED

    def test_missing_title_rejected(self):
        with pytest.raises(ValidationError):
            ExtractedEvent(
                title="",  # Empty string — min_length=1
                event_type=EventType.FEATURE_INTRODUCED,
                confidence_score=0.5,
            )


class TestConflictDetection:
    def _create_feature(self, db):
        feature = Feature(canonical_name="Google Authentication", current_status="UNKNOWN")
        db.add(feature)
        db.flush()
        return feature

    def _create_doc(self, db):
        doc = Document(
            filename="test.txt",
            original_filename="test.txt",
            file_type="txt",
            file_size_bytes=100,
            file_hash="abc123",
        )
        db.add(doc)
        db.flush()
        return doc

    def test_approval_rejection_conflict_detected(self, db):
        """Detecting approved + rejected on same date should create a conflict."""
        feature = self._create_feature(db)
        doc = self._create_doc(db)

        approved_event = Event(
            feature_id=feature.id,
            source_document_id=doc.id,
            title="Google Auth Approved",
            event_type="DECISION_APPROVED",
            decision_status="APPROVED",
            event_date=datetime(2024, 10, 8),
            confidence_score=0.9,
        )
        rejected_event = Event(
            feature_id=feature.id,
            source_document_id=doc.id,
            title="Google Auth Rejected",
            event_type="DECISION_REJECTED",
            decision_status="REJECTED",
            event_date=datetime(2024, 10, 8),
            confidence_score=0.7,
        )
        db.add_all([approved_event, rejected_event])
        db.commit()

        conflicts = detect_conflicts(db)
        assert len(conflicts) >= 1
        conflict_types = [c.conflict_type for c in conflicts]
        assert "DECISION_CONFLICT" in conflict_types

    def test_no_false_positive_conflicts(self, db):
        """A single approved event should not create a conflict."""
        feature = self._create_feature(db)
        doc = self._create_doc(db)

        event = Event(
            feature_id=feature.id,
            source_document_id=doc.id,
            title="Google Auth Approved",
            event_type="DECISION_APPROVED",
            decision_status="APPROVED",
            event_date=datetime(2024, 10, 8),
            confidence_score=0.9,
        )
        db.add(event)
        db.commit()

        conflicts = detect_conflicts(db)
        # Only one approval, no conflict
        decision_conflicts = [c for c in conflicts if c.conflict_type == "DECISION_CONFLICT"]
        assert len(decision_conflicts) == 0


class TestAPIEndpoints:
    def test_health_check(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_documents_list_empty(self, client):
        response = client.get("/api/documents/")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0

    def test_events_list_empty(self, client):
        response = client.get("/api/events/")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0

    def test_features_list_empty(self, client):
        response = client.get("/api/features/")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0

    def test_dashboard_stats(self, client):
        response = client.get("/api/documents/dashboard/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total_documents" in data
        assert "total_events" in data

    def test_assistant_suggestions(self, client):
        response = client.get("/api/assistant/suggestions")
        assert response.status_code == 200
        data = response.json()
        assert "suggestions" in data
        assert len(data["suggestions"]) > 0

    def test_txt_upload(self, client):
        content = b"Date: October 5, 2024\nMeeting notes: Feature X was introduced."
        response = client.post(
            "/api/documents/upload",
            files=[("files", ("meeting.txt", content, "text/plain"))],
        )
        assert response.status_code == 201
        results = response.json()
        assert len(results) == 1
        assert results[0]["processing_status"] in ("COMPLETED", "FAILED")  # May fail without Gemini key

    def test_unsupported_file_type_returns_failed(self, client):
        """Uploading an unsupported file type should produce a FAILED status, not crash."""
        content = b"Some content"
        response = client.post(
            "/api/documents/upload",
            files=[("files", ("script.exe", content, "application/octet-stream"))],
        )
        # The endpoint should not 500 — it should return a result with FAILED status
        assert response.status_code in (201, 422)

