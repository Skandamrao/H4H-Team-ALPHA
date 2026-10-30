@echo off
setlocal
echo ===================================================
echo Starting ChronoGraph AI (Integrated Platform)
echo ===================================================

cd /d "%~dp0backend"
echo [1/3] Checking backend database seed...
python -c "from app.db.database import SessionLocal, Base, engine; from app.models.models import Document; Base.metadata.create_all(bind=engine); db = SessionLocal(); import seed_sample_data; (seed_sample_data.seed() if db.query(Document).count() == 0 else print('Database verified ready.')); db.close()"

echo [2/3] Starting backend server on http://localhost:8000 ...
start "ChronoGraph AI Backend" cmd /c "python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"

timeout /t 2 /nobreak >nul

cd /d "%~dp0frontend"
echo [3/3] Starting frontend server on http://localhost:5173 ...
start "ChronoGraph AI Frontend" cmd /c "npx vite --host 0.0.0.0 --port 5173"

timeout /t 2 /nobreak >nul
echo.
echo ===================================================
echo ChronoGraph AI is live!
echo   Frontend UI:      http://localhost:5173
echo   Backend API:      http://localhost:8000
echo   API Documentation: http://localhost:8000/api/docs
echo ===================================================
start http://localhost:5173

