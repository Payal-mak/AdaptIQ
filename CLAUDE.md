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
| 2 | Database models | Not started |
| 3 | Auth (JWT, roles) | Not started |
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
