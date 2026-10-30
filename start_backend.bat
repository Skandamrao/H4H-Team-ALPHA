@echo off
REM Start ChronoGraph AI backend (Windows)
cd /d "%~dp0backend"

if not exist ".env" (
    echo ERROR: .env file not found.
    echo Copy .env.example to backend\.env and set your GROQ_API_KEY.
    exit /b 1
)

echo Starting ChronoGraph AI backend on http://localhost:8000 ...
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

