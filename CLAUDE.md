# AdaptIQ: An Agentic AI-Based Adaptive Interview Portal

B.Tech final-year project. Read this file at the start of every session.

## Project overview

AdaptIQ is a web portal where students take topic-wise mock interviews conducted by AI agents.

- Topics: DBMS, OS, Computer Networks, OOP, DSA, Java, Python, HR.
- Every topic has questions at 3 levels: Easy, Medium, Hard.
- The interview starts at **Medium**.
- After each answer, an Evaluator Agent scores it out of 10.
- A Difficulty Controller (plain deterministic Python, NOT an LLM) picks the next level.
- Incomplete answers can get a follow-up question.
- At the end, the student gets a topic-wise proficiency level and a feedback report.
- Faculty approve generated questions and can review/override low-confidence scores (human-in-the-loop).

**Roles:** student, faculty, admin.

## Agents (built in later steps)

| Agent | Job |
|---|---|
| Question Bank Agent | Generates questions per topic and level (faculty approve them) |
| Interviewer Agent | Asks questions and follow-ups, runs the conversation |
| Evaluator Agent | Scores each answer out of 10 and gives a confidence value |
| Difficulty Controller | **Deterministic code, not an LLM.** Picks the next level |
| Feedback Agent | Writes the final feedback report and proficiency summary |
| Analytics Agent | Aggregates performance data for students, faculty and admin |

## Adaptive difficulty rules

After each answer, with score `s` out of 10:

- `s >= 7` → move **up** one level (Hard stays Hard)
- `4 <= s <= 6` → **stay** at the same level
- `s < 4` → move **down** one level (Easy stays Easy)

Levels: Easy < Medium < Hard. Start level: Medium.

## Tech stack

- Backend: Python 3.11+, FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2, pytest
- Agents: LangGraph (added in a later step)
- Database: PostgreSQL 16 + pgvector, in Docker (`pgvector/pgvector:pg16` via docker-compose)
- Frontend: React + Vite + TypeScript + Tailwind CSS
- LLM: provider-agnostic. Default Groq (free tier), fallback Google Gemini (free tier). Model names come from `.env`, never hardcoded.
- Environment: Windows + PowerShell, plain `venv` + `pip` + `requirements.txt`.

## Folder structure

```
adaptiq/
├── backend/
│   ├── app/
│   │   ├── main.py         FastAPI app entry
│   │   ├── core/config.py  Settings (pydantic-settings, reads ../.env)
│   │   ├── db/             Database engine and session
│   │   └── api/            Route modules (one file per area)
│   ├── tests/              pytest tests
│   ├── requirements.txt
│   └── pytest.ini
├── frontend/               Vite + React + TS + Tailwind (dev proxy: /api -> :8000)
├── docs/                   Report diagrams
├── docker-compose.yml      PostgreSQL 16 + pgvector
├── .env.example            Template for .env (real .env is git-ignored)
├── README.md
└── CLAUDE.md
```

## Data model (Step 2)

Models live in `backend/app/models/`; schema changes go through Alembic (`backend/alembic/`), never by hand.

- `users` (role: student/faculty/admin), `topics`, `questions` (level, status pending/approved/rejected, `expected_points`)
- `interview_sessions` (one student + topic, `current_level`, final level/score)
- `interview_turns` (question as asked + answer; follow-ups have `is_follow_up` and `parent_turn_id`)
- `evaluations` (one per turn: score 0-10, confidence, `needs_review`, faculty override fields)
- `feedback_reports` (one per session)
- `final_level` / `proficiency_level` use the `Proficiency` enum (beginner/intermediate/advanced); question difficulty uses `Level` (easy/medium/hard). Do not mix them.
- Deleting a session cascades to its turns, evaluations and feedback report (DB `ON DELETE CASCADE` + ORM cascade).
- Enums are stored as strings with CHECK constraints. Each enum column needs a unique constraint name (`enum_type(cls, name)`).
- Not yet built: pgvector embedding column (Step 14), LLM call log table (Step 4).
- Model tests need Docker Postgres running; they use a separate `adaptiq_test` database.

## Auth (Step 3)

- Passwords: Argon2 via `pwdlib` (never passlib). Only the hash is stored.
- Login returns a JWT (PyJWT, HS256) with `sub` (user id), `role`, `exp`. Lifetime: `ACCESS_TOKEN_EXPIRE_MINUTES` (default 120).
- `get_current_user` (`app/api/deps.py`) decodes the token and **reloads the user from the DB**; the DB role is the truth, not the token's role. Missing/invalid/expired token or inactive user -> 401.
- `require_roles(*roles)` -> 403 if the role is not allowed.
- Roles: `student` (self-registers via `POST /api/auth/register`, always student), `faculty` and `admin` (created only by an admin via `POST /api/users`; the first admin via `python -m app.scripts.create_admin`).
- Login failures always say "Invalid email or password" (wrong password, unknown email, inactive user).
- Admins cannot deactivate themselves or remove their own admin role.
- The app refuses to start if `JWT_SECRET` is empty, under 32 chars, or the `change-me...` placeholder (checked at startup in `app/main.py`, not in `Settings`, so Alembic and scripts still run).
- `ALLOWED_EMAIL_DOMAIN` (optional) limits student self-registration only.
- Routes call `app/services/user_service.py`; schemas are in `app/schemas/`. `UserOut` never includes `password_hash`.
- Auth tests need Docker Postgres; `tests/conftest.py` sets a test `JWT_SECRET` so tests don't depend on `.env`.

## Coding rules

1. Type hints everywhere (Python and TypeScript; no `any`).
2. All LLM calls go through ONE wrapper module (built in Step 4). Never call an LLM directly from routes or agents' route handlers.
3. Anything that must be consistent (difficulty rules, eligibility, score aggregation) is plain code with unit tests, never an LLM.
4. Secrets only in `.env`. Never hardcode keys, model names or passwords. `.env` is never committed.
5. Routes stay thin: validate input, call a service/agent, return a response.

## Workflow rules

- Build only what the current step asks. No extra features.
- The user runs all git commands themselves. After each step, give the standard git commit commands; do not run `git` write commands.
- After each step, summarize what changed and explain the key code in simple terms; the user must explain it in a viva.
- At the end of each step, list the exact PowerShell commands to verify it.

## Roadmap

| # | Step | Status |
|---|---|---|
| 1 | Skeleton | Done |
| 2 | Database models | Done |
| 3 | Auth (JWT, roles) | Done |
| 4 | LLM wrapper (retries, Groq -> Gemini fallback, call logging) | Not started |
| 5 | Question Bank Agent | Not started |
| 6 | Evaluator Agent | Not started |
| 7 | Difficulty Controller | Not started |
| 8 | LangGraph interview workflow | Not started |
| 9 | Follow-up questions | Not started |
| 10 | Student UI | Not started |
| 11 | Feedback Agent + student dashboard | Not started |
| 12 | Faculty dashboard | Not started |
| 13 | Analytics | Not started |
| 14 | No-repeat questions with pgvector | Not started |
| 15 | Evaluation study tools | Not started |
| 16 | Voice mode | Not started |
| 17 | Resume-based questions | Not started |
| 18 | Testing + deployment | Not started |
