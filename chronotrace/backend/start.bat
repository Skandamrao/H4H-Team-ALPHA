@echo off
echo ============================================================
echo  ChronoTrace AI — Backend Startup
echo ============================================================
echo.

REM Copy .env.example to .env if not present
if not exist ".env" (
    copy ".env.example" ".env"
    echo Created .env from .env.example — set your API key inside.
)

echo Starting FastAPI server on http://localhost:8000
echo API docs: http://localhost:8000/docs
echo.
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

