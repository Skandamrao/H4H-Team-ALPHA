"""
Cross-platform unified launcher for ChronoGraph AI.
Runs backend, seeds sample data if needed, and starts frontend.

Usage:
  python run_app.py
"""

import os
import sys
import time
import subprocess
import webbrowser

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")
FRONTEND_DIR = os.path.join(ROOT_DIR, "frontend")

def main():
    print("=" * 60)
    print("  ChronoGraph AI — Temporal Product Knowledge System")
    print("=" * 60)

    # 1. Verify / Seed Database
    print("\n[1/3] Verifying database status...")
    seed_script = os.path.join(BACKEND_DIR, "seed_sample_data.py")
    db_file = os.path.join(BACKEND_DIR, "chronograph.db")
    if not os.path.exists(db_file):
        print("  Seeding demonstration dataset...")
        subprocess.run([sys.executable, seed_script], cwd=BACKEND_DIR)
    else:
        print("  Database verified.")

    # 2. Launch Backend
    print("\n[2/3] Launching FastAPI backend on http://localhost:8000 ...")
    backend_cmd = [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
    backend_proc = subprocess.Popen(backend_cmd, cwd=BACKEND_DIR)

    time.sleep(2)

    # 3. Launch Frontend
    print("\n[3/3] Launching Vite frontend on http://localhost:5173 ...")
    npx_cmd = "npx.cmd" if sys.platform == "win32" else "npx"
    frontend_cmd = [npx_cmd, "vite", "--host", "0.0.0.0", "--port", "5173"]
    frontend_proc = subprocess.Popen(frontend_cmd, cwd=FRONTEND_DIR)

    time.sleep(2)

    print("\n" + "=" * 60)
    print("  All services integrated and running!")
    print("  • Web UI:          http://localhost:5173")
    print("  • Backend API:     http://localhost:8000")
    print("  • Interactive API: http://localhost:8000/api/docs")
    print("=" * 60 + "\n")

    try:
        webbrowser.open("http://localhost:5173")
    except Exception:
        pass

    try:
        backend_proc.wait()
        frontend_proc.wait()
    except KeyboardInterrupt:
        print("\nStopping services...")
        backend_proc.terminate()
        frontend_proc.terminate()
        print("Shutdown complete.")

if __name__ == "__main__":
    main()

