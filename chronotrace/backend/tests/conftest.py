"""
Pytest root conftest — adds the backend/ directory to sys.path so that
'from app.xxx import ...' works without installing the package.
Also provides a minimal .env for testing (no real API keys needed for unit tests).
"""
import sys
import os

# Ensure 'app' package is importable
sys.path.insert(0, os.path.dirname(__file__))

# Minimal env vars so pydantic-settings doesn't fail on missing .env
os.environ.setdefault("LLM_PROVIDER", "gemini")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_chronotrace.db")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173")
