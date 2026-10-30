"""
Pytest configuration and fixtures for ChronoGraph AI backend tests.
"""

import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Use an in-memory SQLite database for tests
TEST_DATABASE_URL = "sqlite://"

# Set env vars before importing the app
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["GEMINI_API_KEY"] = "test_key_not_real"
os.environ["UPLOAD_DIR"] = "/tmp/chronograph_test_uploads"
os.environ["LOG_FILE"] = "/tmp/chronograph_test.log"

from app.main import app
from app.db.database import Base, get_db

engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def create_tables():
    """Create all tables before each test, drop them after."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    """Yield a fresh database session for direct ORM access in tests."""
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db):
    """FastAPI test client with the test DB injected."""
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

