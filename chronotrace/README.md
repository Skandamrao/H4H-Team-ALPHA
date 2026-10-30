# ChronoTrace AI — Temporal Product Knowledge System

> **PS2 — Temporal Product Knowledge System**  
> National Hackathon Project · Team ALPHA

ChronoTrace AI is a full-stack, temporal product knowledge system that ingests dated project records (meeting notes, design specifications, email threads, ADRs, changelogs) and deterministically reconstructs the historical evolution of software features and modules.

---

## Key Capabilities & Mandatory Requirements Covered

1. **Multi-Source Record Ingestion (R1)**: Ingests meeting notes, design specs, email threads, decision logs, and changelogs.
2. **Feature & Decision Extraction (R2)**: Extracts canonical features, modules, explicit decisions, actors, and confidence metrics.
3. **Lifecycle Tracking (R3)**: Tracks introductions, modifications, renames, and removals across software evolution.
4. **Strict State Distinction (R4 & Rules A/B)**: Explicitly separates `PROPOSED`, `APPROVED`, `REJECTED`, and `IMPLEMENTED`. Approval is never confused with implementation.
5. **Source Provenance & Verifiable Evidence (R5 & Rule H)**: Every historical event and QA answer links directly to its source ID and exact textual quotation.
6. **Triple-Date Separation (R6 & Rule C)**: Segregates `event_date`, `source_date`, and `ingestion_timestamp`. Unknown event dates are never defaulted to system ingestion time.
7. **Chronological Timelines & Gaps (R7 & Rule G)**: Renders feature milestones, detects gaps, and reconstructs state as-of any event date or ingestion knowledge cutoff.
8. **Evidence-Grounded Question Answering (R8)**: Answering questions with deterministic pre-retrieval, source citation validation, and clear answer statuses (`SUPPORTED`, `PARTIALLY_SUPPORTED`, `CONFLICTED`, `INSUFFICIENT_EVIDENCE`).
9. **Conflict Detection (R9 & Rule F)**: Differentiates normal progressions (Proposed → Approved → Implemented) from genuine contradictions (concurrent Approved + Rejected, Implemented before Proposed).
10. **Append-Only Incremental Ingestion (R10 & Rule D)**: Ingests later update batches without mutating historical records.

---

## Tech Stack

- **Frontend**: React 19, TypeScript, Vite, Tailwind CSS, React Flow (interactive graph), Lucide Icons, Axios, Zustand.
- **Backend**: Python 3.14, FastAPI, SQLAlchemy 2.0 (asyncio + aiosqlite), Pydantic v2, python-dateutil.
- **AI**: Configurable Gemini (`google-generativeai`) or OpenAI (`openai`).
- **Testing**: Pytest, pytest-asyncio, anyio, HTTPX.

---

## Getting Started

### 1. Backend Setup

```bash
cd backend
copy .env.example .env
# Edit .env and supply GEMINI_API_KEY or OPENAI_API_KEY
python -m pip install -r requirements.txt
./start.bat
# API server runs at http://localhost:8000
# OpenAPI documentation at http://localhost:8000/docs
```

### 2. Frontend Setup

```bash
cd frontend
npm install
./start.bat
# Frontend web interface runs at http://localhost:5173
```

### 3. Running Test Suites

```bash
cd backend
python -m pytest -v
# Output: 17 passed
```

### 4. Ingesting Datasets & Fixtures

Navigate to the **Ingest** tab in the web UI (http://localhost:5173/ingest) or post directly to `/api/ingest`. Two pre-built realistic batches are ready in `backend/fixtures/`:
- `batch1_records.json`: Q1 Sprint planning, OAuth2 spec, Data Export design notes, Auth v2.2 release, and Search ADR.
- `batch2_records.json`: Incremental update containing Data Export v1.0, Q2 Search transition (Elasticsearch rename), and Apple Sign-In rejection ADR.

