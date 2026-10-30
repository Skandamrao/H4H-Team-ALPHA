@echo off
REM Start ChronoGraph AI frontend (Windows)
cd /d "%~dp0frontend"
echo Starting ChronoGraph AI frontend on http://localhost:5173 ...
npx vite --host 0.0.0.0 --port 5173
