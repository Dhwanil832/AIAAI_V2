# AI-AAI: AI-Assisted Accident Investigation & Reporting

---

## Overview

AI-AAI is a fully on-premise, conversational AI system for workplace safety incident reporting in steel manufacturing environments. It replaces manual OSHA-style forms with a multi-agent LLM pipeline — no cloud, no external APIs, everything runs locally.

**Stack at a glance:** FastAPI · PostgreSQL 16 · React/Vite · Ollama · Qdrant · MinIO · faster-whisper

---

## Table of Contents

1. [Install Required Software](#1-install-required-software)
2. [Set Up External Services](#2-set-up-external-services)
3. [Clone the Repository](#3-clone-the-Repository)
4. [Set Up the Backend](#4-set-up-the-backend)
5. [Set Up the Frontend](#5-set-up-the-frontend)
6. [Starting Everything](#6-starting-everything)
7. [First-Time App Setup](#7-first-time-app-setup)
8. [Service Port Reference](#8-service-port-reference)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. Install Required Software

Install each of the following. Links are provided for the exact versions used in development.

### Python (Anaconda)

Anaconda is recommended for environment isolation.

**Download:** https://www.anaconda.com/download

Install with default settings. After install, open **Anaconda Prompt** for all Python-related steps.

---

### Node.js

Required to run the React frontend.

**Download:** https://nodejs.org/en/download (choose the LTS version)

Verify install:
```bash
node -v
npm -v
```

---

### PostgreSQL 16

The main relational database.

**Download:** https://www.enterprisedb.com/downloads/postgres-postgresql-downloads

During installation:
- Set a password for the `postgres` superuser — **write it down**, you'll need it
- Keep the default port: **5432**
- Install **pgAdmin 4** when offered (useful for inspecting the database)

After install, open **pgAdmin 4** or **psql** and create the application database:

```sql
CREATE DATABASE safety_chatbot_db;
```

---

### Ollama

Runs the local LLM (qwen3.5:9b) entirely on your machine.

**Download:** https://ollama.com/download

Install, then open a terminal and pull the required model:

```bash
ollama pull qwen3.5:9b
ollama pull nomic-embed-text
```

> **Note:** `qwen3.5:9b` is ~6 GB. `nomic-embed-text` (~275 MB) is used for vector embeddings in Qdrant. Both downloads require an internet connection the first time.

Verify Ollama is running:
```bash
ollama list
```

---

### Qdrant

The vector search engine for semantic similarity search across historical incidents.

**Download:** https://github.com/qdrant/qdrant/releases/latest

1. Download the Windows binary: `qdrant-x86_64-pc-windows-msvc.zip`
2. Extract it to `C:\qdrant\`
3. You should have `C:\qdrant\qdrant.exe`

Run it:
```bash
C:\qdrant\qdrant.exe
```

Qdrant will start on port **6333** (HTTP) and **6334** (gRPC). You can verify it's running by visiting http://localhost:6333/dashboard in your browser.

> Warnings about the config file or filesystem type check on first launch are **harmless**.

---

### MinIO

On-premise S3-compatible object storage for uploaded files and photos.

**Download:** https://min.io/download#/windows

1. Download the Windows binary (`minio.exe`)
2. Move it to `C:\minio\minio.exe`
3. Create a data directory: `C:\minio\data`

Run it:
```bash
C:\minio\minio.exe server C:\minio\data --console-address :9001
```

MinIO starts on port **9000** (API) and **9001** (web console). Default credentials are:
- **Access Key**: `minioadmin`
- **Secret Key**: `minioadmin`

Verify by visiting http://localhost:9001 in your browser.

> The `.bloomcycle.bin` prefix access error on startup is **harmless**.

---

## 2. Set Up External Services

Once Ollama, Qdrant, and MinIO are installed, make sure they are running **before** starting the backend. The backend connects to all three at startup.

Start each in a separate terminal window:

**Terminal 1 — Ollama:**
```bash
ollama serve
```
> Ollama may already be running as a system tray app after installation. Check before running this.

**Terminal 2 — Qdrant:**
```bash
C:\qdrant\qdrant.exe
```

**Terminal 3 — MinIO:**
```bash
C:\minio\minio.exe server C:\minio\data --console-address :9001
```

**PostgreSQL** runs as a Windows service and starts automatically after installation. No manual start needed.

---

## 3. Clone the Repository

```bash
git clone https://github.com/your-org/safety-chatbot.git
cd safety-chatbot
```

---

## 4. Set Up the Backend

### Create the Conda Environment

Open **Anaconda Prompt** from the Start menu:

```bash
conda create -n safety-chatbot python=3.11 -y
conda activate safety-chatbot
```

### Install Python Dependencies

```bash
cd path\to\safety-chatbot\backend
pip install -r requirements.txt
```

If a `requirements.txt` is not present, install the core packages manually:

```bash
pip install fastapi uvicorn sqlalchemy alembic psycopg2-binary python-jose passlib bcrypt python-multipart pydantic-settings qdrant-client minio httpx pandas openpyxl faster-whisper
```

### Run Database Migrations

With the conda environment active and PostgreSQL running:

```bash
cd backend
alembic upgrade head
```

This creates all tables in `safety_chatbot_db`. You should see a series of migration steps complete without errors.

> **If you see `relation already exists` errors**, your database may have leftover tables from a previous run. The safest fix is to drop and recreate the database in pgAdmin, then re-run `alembic upgrade head`.

### Reset PostgreSQL Sequences (After Bulk Data Migration Only)

If you've imported existing data from another database, sequences may be out of sync. Run these in psql or pgAdmin:

```sql
SELECT setval('incident_reports_id_seq', (SELECT MAX(id) FROM incident_reports));
SELECT setval('unfinished_reports_id_seq', (SELECT MAX(id) FROM unfinished_reports));
SELECT setval('users_id_seq', (SELECT MAX(id) FROM users));
```

---

## 5. Set Up the Frontend

Open a new terminal (standard Command Prompt or PowerShell is fine):

```bash
cd path\to\safety-chatbot\frontend
npm install
```

This installs all React dependencies from `package.json`.

---

## 6. Starting Everything

You need **five things running** simultaneously. Use five separate terminal windows.

| Terminal | Command | What It Does |
|---|---|---|
| 1 | `ollama serve` | LLM inference server |
| 2 | `C:\qdrant\qdrant.exe` | Vector search engine |
| 3 | `C:\minio\minio.exe server C:\minio\data --console-address :9001` | Object storage |
| 4 | `cd backend && uvicorn main:app --reload --port 8000` | FastAPI backend |
| 5 | `cd frontend && npm run dev` | React frontend (Vite) |

> PostgreSQL runs as a background Windows service — no terminal needed.

For Terminal 4 (backend), make sure your conda environment is active first:
```bash
conda activate safety-chatbot
cd path\to\safety-chatbot\backend
uvicorn main:app --reload --port 8000
```

Once everything is running, open your browser to:

**http://localhost:5173**

---

## 7. First-Time App Setup

### Create the First Admin Account

On first launch, navigate to http://localhost:5173 and you will see a setup screen to create the initial admin account. This route is only available when no users exist in the database.

Alternatively, call the setup endpoint directly:
```bash
curl -X POST http://localhost:8000/auth/setup \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "yourpassword", "job_title": "Safety Manager"}'
```

### Upload Historical Incident Data (Optional)

Log in as admin, navigate to the **Admin** page, and use the historical data upload section to import `.xls` / `.xlsx` files of past incidents. The system supports three incident types: Personal Injuries, Near Miss, and Equipment Damage.

> Column headers in the XLS files should start at row 5 (0-indexed row 4). The system maps known column names automatically.

### Backfill Qdrant Vector Embeddings (Optional)

After uploading historical data, run the backfill script to embed all records into Qdrant for semantic similarity search:

```bash
conda activate safety-chatbot
cd backend
python scripts/backfill_qdrant.py
```

This uses `nomic-embed-text` (via Ollama) to embed each incident and store it in the `incident_reports` Qdrant collection.

---

## 8. Service Port Reference

| Service | Port | URL | Notes |
|---|---|---|---|
| PostgreSQL | 5432 | — | Windows service, auto-starts |
| Ollama | 11434 | http://localhost:11434 | LLM inference |
| Qdrant | 6333 | http://localhost:6333/dashboard | Vector search |
| MinIO API | 9000 | — | S3-compatible API |
| MinIO Console | 9001 | http://localhost:9001 | Web UI |
| FastAPI | 8000 | http://localhost:8000/docs | Backend + Swagger UI |
| React (Vite) | 5173 | http://localhost:5173 | Frontend app |

---

## 9. Troubleshooting

### `alembic upgrade head` fails with "column already exists"
The database has a partial schema from a previous state. Drop all tables (or drop and recreate the database), then re-run the migration.

### Backend starts but Ollama calls time out
Make sure Ollama is running (`ollama serve`) and the model is downloaded (`ollama list`). The model name in `.env` must match exactly — e.g., `qwen3.5:9b`.

### Qdrant connection refused
Qdrant is not running. Start it with `C:\qdrant\qdrant.exe`. If the port is blocked, check Windows Firewall settings for port 6333.

### MinIO errors on file upload
Confirm MinIO is running and the `safety-chatbot` bucket exists. The bucket is created automatically on backend startup — if it's missing, the backend may not have started cleanly. Check the backend terminal for startup errors.

### FastAPI returns 422 on report export or witness routes
Route ordering issue. Specific routes like `/reports/export` and `/witness-pending` must be registered **before** parameterized routes like `/{report_id}` in `routers/reports.py`. Check that route order is correct.

### PostgreSQL sequence errors after data import (`duplicate key value`)
Run the `setval()` commands in [Section 5](#5-set-up-the-backend) to resync PostgreSQL sequences.

### `NaN` values causing PostgreSQL JSON insert failures
Historical XLS files with empty cells produce Python `float('nan')` values which PostgreSQL JSON columns reject. The sanitizer in the upload pipeline handles this automatically. If you see this error outside of historical upload, ensure `_sanitize_for_json()` is applied to all JSON fields before insert.

---

