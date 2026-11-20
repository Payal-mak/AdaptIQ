# AdaptIQ: An Agentic AI-Based Adaptive Interview Portal

Topic-wise mock interviews run by AI agents, with difficulty that adapts to each answer. See [CLAUDE.md](CLAUDE.md) for the full overview and roadmap.

All commands below are for **Windows PowerShell**, run from the project root (`d:\adaptiq`) unless stated.

## Prerequisites

Python 3.11+, Node.js 20+, Docker Desktop (running).

## 1. Create your .env

```powershell
Copy-Item .env.example .env
```

Open `.env` and fill in values. For Step 1 only `DATABASE_URL` matters, and the default already matches docker-compose.

## 2. Start the database

```powershell
docker compose up -d
docker compose ps        # STATUS should become "healthy"
```

Stop it later with `docker compose down` (data is kept in a volume).

## 3. Backend setup

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If PowerShell blocks the activate script, run once:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

## 4. Run the backend

```powershell
cd backend
.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

Check: http://localhost:8000/api/health should show `{"status":"ok","database":"ok"}`. API docs: http://localhost:8000/docs

## 5. Run the frontend (new terminal)

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. It should show **Backend: OK** and **Database: OK**.

## 6. Run tests

```powershell
cd backend
.venv\Scripts\Activate.ps1
pytest
```

The tests do not need Docker.
