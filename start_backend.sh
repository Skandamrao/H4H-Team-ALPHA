#!/usr/bin/env bash
# Start ChronoGraph AI backend (development mode)
set -e

cd "$(dirname "$0")/backend"

if [ ! -f ".env" ]; then
  echo "ERROR: .env file not found."
  echo "Copy .env.example to backend/.env and add your GEMINI_API_KEY."
  exit 1
fi

echo "Starting ChronoGraph AI backend on http://localhost:8000 ..."
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

