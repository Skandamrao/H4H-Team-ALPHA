# ChronoGraph AI

> **AI-Powered Temporal Product Knowledge System**  
> *Built for Hackathon Problem Statement 2*

ChronoGraph AI reconstructs the historical evolution of software features from dated project documents (meeting notes, architecture decision records, pull requests, and tickets). It extracts discrete events, tracks features across renames, builds a temporal knowledge graph, and enables **"time-travel" state reconstruction** backed by zero-hallucination citations.

---

## 🚀 Quick Start

### Option 1: One-Click Run (Windows)
Double-click or run:
```cmd
run_app.bat
```
*This verifies the database, starts the backend on port 8000, starts the frontend on port 5173, and opens your browser.*

### Option 2: Cross-Platform Python Launcher
```bash
python run_app.py
```

### Option 3: Manual Start (Separate Terminals)

**Terminal 1 — Backend:**
```cmd
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**Terminal 2 — Frontend:**
```cmd
cd frontend
npx vite --host 127.0.0.1 --port 5173
```

- **Web App**: [http://localhost:5173](http://localhost:5173)
- **API & Docs**: [http://localhost:8000/api/docs](http://localhost:8000/api/docs)

---

## 💡 What ChronoGraph AI Does

1. **Document Ingestion**:
   - Upload **PDF, TXT, Markdown, and JSON** files.
   - Computes **SHA-256** checksums to detect duplicate files.
   - **Separates Event Date from Ingestion Date**: A meeting note from *October 5* uploaded on *October 30* preserves October 5 as its historical date.
   - Clean document deletion with cascading cleanup of events and graph edges.

2. **AI Event Extraction**:
   - Uses **Google Gemini API** (`gemini-2.5-flash`) with automatic **Groq AI** fallback (`gpt-oss-120b` / `20b`) in structured JSON mode.
   - Strict lifecycle separation:
     - `PROPOSED`: Feature was proposed (e.g. in a meeting).
     - `APPROVED`: Architecture consensus granted.
     - `IMPLEMENTED`: Working code merged or deployed.
     - `REMOVED` / `DEPRECATED`: Feature retired.
   - A proposal is never assumed to be approved; an approval is never assumed to be implemented.

3. **Entity Resolution & Alias Tracking**:
   - Features often change names (e.g. `"Google Login"` ➔ `"Google OAuth"` ➔ `"Google Authentication"`).
   - Uses **RapidFuzz** fuzzy matching to unify aliases under one canonical feature without losing past name history.

4. **Temporal Knowledge Graph**:
   - Built with **NetworkX** and persisted in **SQLite**.
   - Nodes: `Feature`, `Module`, `Event`, `Decision`, `Document`, `Person`.
   - Relationships: `FEATURE_HAS_EVENT`, `EVENT_SUPPORTED_BY`, `DECISION_RELATES_TO`, `FEATURE_BELONGS_TO_MODULE`, `EVENT_FOLLOWS_EVENT`.
   - Rendered interactively with **React Flow**.

5. **Historical State Reconstruction (Time Travel)**:
   - Answers: *"What was the state of authentication on October 10, 2024?"*
   - Select an **"As of date"** in the Timeline Explorer.
   - Strictly ignores all events after that date, showing the exact reconstructed status at that point in time.

6. **Evidence-Backed Historical AI Assistant**:
   - Answers questions strictly using recorded project evidence.
   - Provides **verbatim document excerpts** and source citations.
   - Refuses to invent missing facts (returns `"Insufficient"` confidence if no records match).
   - Includes deterministic offline database fallback.

7. **Conflict Detection**:
   - Automatically flags contradictory decisions (e.g., approved and rejected close in date, or implemented before approved) without deleting historical records.

---

## 🛠️ Technology Stack

| Layer | Tools |
|---|---|
| **Frontend** | React 18, TypeScript, Vite, Tailwind CSS, React Flow, Recharts, Lucide Icons |
| **Backend** | Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy, Uvicorn |
| **Database** | SQLite (embedded, persistent) |
| **Graph** | NetworkX (in-memory temporal multi-graph) |
| **Document Parsing** | PyMuPDF (PDF), native Python (TXT, MD, JSON) |
| **Entity Matching** | RapidFuzz (Levenshtein similarity) |
| **AI Providers** | Google Gemini API (`gemini-2.5-flash`) + Groq AI (`gpt-oss-120b` / `20b`) |

---

## 📁 Project Structure

```
chronograph-ai/
├── backend/
│   ├── app/
│   │   ├── api/routes/          # API endpoints (documents, timeline, graph, assistant...)
│   │   ├── core/config.py       # App settings & environment variables
│   │   ├── db/database.py       # SQLite connection & session
│   │   ├── models/models.py     # SQLAlchemy ORM models
│   │   ├── schemas/schemas.py   # Pydantic validation schemas
│   │   └── services/            # Ingestion, AI extraction, entity resolution, graph, assistant
│   ├── sample_data/             # Synthetic test documents (.txt, .md, .json)
│   ├── chronograph.db           # SQLite database
│   ├── requirements.txt         # Python dependencies
│   └── run_tests.py             # Backend test runner (11 tests)
│
├── frontend/
│   ├── src/
│   │   ├── pages/               # Dashboard, Documents, Features, Timeline, Graph, Assistant
│   │   ├── components/          # Reusable UI components
│   │   └── lib/api.ts           # Typed API client
│   └── package.json             # Frontend dependencies & scripts
│
├── run_app.bat                  # One-click Windows starter
├── run_app.py                   # One-click Python starter
└── README.md                    # Project documentation
```

---

## 📡 Key API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Health check (`{"status": "ok"}`) |
| `POST` | `/api/documents/upload` | Upload files (PDF/TXT/MD/JSON) & extract events |
| `GET` | `/api/documents/` | List all ingested documents |
| `DELETE` | `/api/documents/{id}` | Delete a document and its events (cascade) |
| `GET` | `/api/documents/dashboard/stats` | Dashboard metrics & event breakdown |
| `GET` | `/api/features/` | List canonical features & aliases |
| `GET` | `/api/timeline/{feature_id}` | Feature history (supports `?to_date=YYYY-MM-DD` for time travel) |
| `GET` | `/api/graph/` | Knowledge graph nodes & edges |
| `POST` | `/api/graph/rebuild` | Rebuild graph from database |
| `POST` | `/api/assistant/ask` | Ask historical questions with citations |
| `GET` | `/api/assistant/suggestions` | Dynamic suggested questions from database |
| `GET` | `/api/conflicts/` | List detected historical conflicts |

---

## 🧪 Testing

To run the automated backend test suite:

```cmd
cd backend
python run_tests.py
```

**Results**: `11/11 tests passing` covering file validation, SHA-256 deduplication, date inference, entity resolution, Pydantic validation, conflict detection, graph construction, and anti-hallucination assistant guardrails.

---

## 🎯 Hackathon Demonstration Flow

1. **Dashboard** (`/dashboard`): Show system counters and event distribution chart.
2. **Document Manager** (`/documents`): Upload a sample file from `backend/sample_data/`. Show instant processing and duplicate detection.
3. **Timeline Explorer** (`/timeline`): Pick a feature (e.g. *Google Authentication*), select an **"As of date"** (e.g. `2024-10-06`) to demonstrate **Historical State Reconstruction** (past events shown, future events excluded).
4. **Knowledge Graph** (`/graph`): Explore the interactive React Flow visual graph and click nodes to view details.
5. **AI Assistant** (`/assistant`): Ask a question to demonstrate grounded answers with exact document citations.
