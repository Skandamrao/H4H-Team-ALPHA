"""
Test runner for ChronoGraph AI.
Can be run with pytest: `pytest tests/`
or standalone: `python run_tests.py`
"""

import sys
import os
import unittest

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["GEMINI_API_KEY"] = ""
os.environ["GROQ_API_KEY"] = ""
os.environ["UPLOAD_DIR"] = "./test_uploads"
os.environ["LOG_FILE"] = "./test.log"


class TestDocumentProcessor(unittest.TestCase):
    def test_file_type_validation(self):
        from app.services.document_processor import validate_file_type
        self.assertTrue(validate_file_type("notes.txt")[0])
        self.assertTrue(validate_file_type("doc.md")[0])
        self.assertTrue(validate_file_type("data.json")[0])
        self.assertTrue(validate_file_type("paper.pdf")[0])
        self.assertFalse(validate_file_type("malware.exe")[0])

    def test_file_hashing(self):
        from app.services.document_processor import compute_file_hash
        content = b"ChronoGraph Historical AI Test"
        h1 = compute_file_hash(content)
        h2 = compute_file_hash(content)
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 64)

    def test_text_extraction(self):
        from app.services.document_processor import extract_text
        txt_res, _ = extract_text(b"Feature X was introduced on Oct 5.", "txt")
        self.assertIn("Feature X", txt_res)
        json_res, _ = extract_text(b'{"key": "value"}', "json")
        self.assertIn("key", json_res)

    def test_date_inference(self):
        from app.services.document_processor import infer_document_date
        d, conf = infer_document_date("Date: October 8, 2024\nMeeting record.", "notes.txt")
        self.assertIsNotNone(d)
        self.assertEqual(d.year, 2024)
        self.assertEqual(d.month, 10)
        self.assertEqual(d.day, 8)
        self.assertEqual(conf, "HIGH")


class TestEntityResolution(unittest.TestCase):
    def setUp(self):
        from app.db.database import Base, engine, SessionLocal
        Base.metadata.create_all(bind=engine)
        self.db = SessionLocal()

    def tearDown(self):
        from app.db.database import Base, engine
        self.db.close()
        Base.metadata.drop_all(bind=engine)

    def test_normalise_name(self):
        from app.services.entity_resolution import normalise_name
        self.assertEqual(normalise_name("Google OAuth 2.0!"), "google oauth 2 0")

    def test_resolve_or_create_feature(self):
        from app.services.entity_resolution import resolve_or_create_feature
        f1, created1 = resolve_or_create_feature(self.db, "Google Authentication", None, None)
        self.db.commit()
        self.assertTrue(created1)

        f2, created2 = resolve_or_create_feature(self.db, "Google Authentication", None, None)
        self.db.commit()
        self.assertFalse(created2)
        self.assertEqual(f1.id, f2.id)


class TestSchemas(unittest.TestCase):
    def test_extracted_event_validation(self):
        from app.schemas.schemas import ExtractedEvent, EventType, DecisionStatus
        ev = ExtractedEvent(
            title="Google OAuth Approved",
            event_type=EventType.DECISION_APPROVED,
            decision_status=DecisionStatus.APPROVED,
            confidence_score=0.95,
        )
        self.assertEqual(ev.title, "Google OAuth Approved")
        self.assertEqual(ev.decision_status, DecisionStatus.APPROVED)

    def test_invalid_event_type(self):
        from app.schemas.schemas import ExtractedEvent
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            ExtractedEvent(title="Test", event_type="UNKNOWN_TYPE")


class TestConflictAndGraph(unittest.TestCase):
    def setUp(self):
        from app.db.database import Base, engine, SessionLocal
        Base.metadata.create_all(bind=engine)
        self.db = SessionLocal()

    def tearDown(self):
        from app.db.database import Base, engine
        self.db.close()
        Base.metadata.drop_all(bind=engine)

    def test_conflict_detection_approved_and_rejected(self):
        from datetime import datetime
        from app.models.models import Feature, Event, Document
        from app.services.conflict_detector import detect_conflicts

        doc = Document(
            filename="notes.txt",
            original_filename="notes.txt",
            file_type="txt",
            file_size_bytes=120,
            file_hash="hash123",
        )
        self.db.add(doc)
        self.db.flush()

        feat = Feature(canonical_name="Google Authentication")
        self.db.add(feat)
        self.db.flush()

        e_appr = Event(
            feature_id=feat.id,
            source_document_id=doc.id,
            title="Approved Google Auth",
            event_type="DECISION_APPROVED",
            decision_status="APPROVED",
            event_date=datetime(2024, 10, 8),
            confidence_score=0.9,
        )
        e_rej = Event(
            feature_id=feat.id,
            source_document_id=doc.id,
            title="Rejected Google Auth",
            event_type="DECISION_REJECTED",
            decision_status="REJECTED",
            event_date=datetime(2024, 10, 8),
            confidence_score=0.8,
        )
        self.db.add_all([e_appr, e_rej])
        self.db.commit()

        conflicts = detect_conflicts(self.db)
        self.assertGreaterEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].conflict_type, "DECISION_CONFLICT")

    def test_knowledge_graph_build(self):
        from app.services.graph.knowledge_graph import rebuild_graph
        graph = rebuild_graph(self.db)
        json_graph = graph.to_json_graph()
        self.assertIn("nodes", json_graph)
        self.assertIn("edges", json_graph)


    def test_assistant_grounded_answer(self):
        from app.services.historical_assistant import get_assistant
        from app.models.models import Feature, Event, Document
        from datetime import datetime

        doc = Document(
            filename="notes.txt",
            original_filename="notes.txt",
            file_type="txt",
            file_size_bytes=100,
            file_hash="hash999",
        )
        self.db.add(doc)
        self.db.flush()

        feat = Feature(canonical_name="Google Authentication")
        self.db.add(feat)
        self.db.flush()

        e = Event(
            feature_id=feat.id,
            source_document_id=doc.id,
            title="Google Login Integration Proposed",
            description="Marcus Rivera proposed introducing Google Login.",
            event_type="DECISION_PROPOSED",
            decision_status="PROPOSED",
            reason="User research shows 72% of target users have Google accounts.",
            event_date=datetime(2024, 10, 5),
            confidence_score=0.95,
            supporting_text="Marcus Rivera proposed introducing Google Login.",
        )
        self.db.add(e)
        self.db.commit()

        assistant = get_assistant()
        ans = assistant.answer(self.db, "Why was Google authentication introduced?")
        self.assertIn("Google", ans.answer)
        self.assertGreater(len(ans.supporting_evidence), 0)
        self.assertEqual(ans.supporting_evidence[0].document_filename, "notes.txt")

        # Unknown question should decline to invent history
        ans_unk = assistant.answer(self.db, "Why was quantum blockchain added?")
        self.assertEqual(ans_unk.confidence, "Insufficient")


if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTest(loader.loadTestsFromTestCase(TestDocumentProcessor))
    suite.addTest(loader.loadTestsFromTestCase(TestEntityResolution))
    suite.addTest(loader.loadTestsFromTestCase(TestSchemas))
    suite.addTest(loader.loadTestsFromTestCase(TestConflictAndGraph))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
