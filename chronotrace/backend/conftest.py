"""
Root conftest — sets env vars before any app module is imported.
Placing this at backend/ root ensures it runs before test collection.
"""
import os

os.environ.setdefault("LLM_PROVIDER", "gemini")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_chronotrace.db")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173")

