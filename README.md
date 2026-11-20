# AdaptIQ: An Agentic AI-Based Adaptive Interview Portal

Topic-wise mock interviews run by AI agents, with difficulty that adapts to each answer. See [CLAUDE.md](CLAUDE.md) for the full overview and roadmap.

All commands below are for **Windows PowerShell**, run from the project root (`d:\adaptiq`) unless stated.

## Prerequisites

Python 3.11+, Node.js 20+, Docker Desktop (running).

## 1. Create your .env

```powershell
Copy-Item .env.example .env
```

Open `.env` and fill in values. `DATABASE_URL` already matches docker-compose.

**`JWT_SECRET` is required.** The backend refuses to start if it is empty, shorter than 32 characters, or still the placeholder. Generate one and paste it into `.env`:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Optional: set `ALLOWED_EMAIL_DOMAIN=college.edu` to limit student self-registration to that email domain (empty = any email).

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

Most tests need the Docker database running (they use a separate `adaptiq_test` database, created automatically). If Docker is off, those tests are skipped.

## 7. Create the first admin and try login

Run migrations and seed topics once (database must be running):

```powershell
cd backend
.venv\Scripts\Activate.ps1
alembic upgrade head
python -m app.db.seed
python -m app.scripts.create_admin     # asks for email, name, password (typing is hidden)
```

Start the backend (`uvicorn app.main:app --reload`), then open http://localhost:8000/docs and:

1. Click **Authorize** (top right). Enter your admin **email in the `username` box** and your password. Leave client_id/client_secret empty. Click Authorize, then Close.
2. Open `GET /api/auth/me` -> **Try it out** -> **Execute**. It should return your admin user (no password in the response).
3. Open `POST /api/users` and create a faculty account with `"role": "faculty"`.
4. To test a student: call `POST /api/auth/register` (no login needed), then click Authorize again with the student's email and password. `GET /api/users` should now return **403**.
