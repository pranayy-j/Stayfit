# StayFit

Food-fitness tracker. Two independent projects:
- `backend/`: Python 3.12, FastAPI, SQLAlchemy 2, Alembic, uv. Postgres on Neon.
- `frontend/`: Expo / React Native (TypeScript). Rules in `frontend/AGENTS.md`, loaded via `frontend/CLAUDE.md`.

## Backend architecture
- Layers: `controllers/` → `services/` → `repositories/`. Each layer calls only the one below it.
  - Controllers: HTTP only. Parse the request, call a service, map domain errors to status codes.
  - Services: business logic and external integrations. Own transactions (`commit`/`rollback`). No HTTP.
  - Repositories: DB queries and `add`/`flush` only. No business rules, no commits.
- ORM models live in `app/models/`; Pydantic request/response models live in `app/schemas/`. Keep them separate.
- Follow the Single Responsibility Principle: one job per module, class, and function.
- Every route declares a Pydantic response model. Document error responses via `responses=` with `ErrorResponse`.
- Endpoints that many users call at once must be async, end to end (`AsyncSession` via `get_async_db`).
  Don't hold a DB connection while waiting on slow external calls.

## AI / agentic workflows: LangGraph and LangChain first
- Build every AI or agentic workflow with LangGraph and LangChain by default.
  - Multi-step flows: a `StateGraph` in `app/workflows/`, one node per step. Pass per-request dependencies
    (e.g. `AsyncSession`) through the runtime `context`, not through state. The calling service commits.
  - Model or provider calls: use the LangChain integration package (e.g. `langchain-typesafe` for JEV).
    Add retries with `.with_retry()`, for transient errors only.
- Use a raw provider SDK only when no LangChain integration exists or it can't do what's needed, and say so.
- Don't force LangGraph onto non-AI code (auth, CRUD, controllers).
- Prompts and criteria given by the product owner are passed verbatim. Don't reword them.
- Never log user transcripts or other personal content. Log scores, IDs, and model names only.

## Commands (run from `backend/`)
```bash
uv sync
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
uv run pytest -q                                         # needs local Postgres: docker compose up -d
uv run ruff check . && uv run ruff format --check .
uv run alembic revision --autogenerate -m "describe change"
uv run alembic upgrade head                              # applies to the Neon DB in .env.local
```
Run tests and ruff before declaring a backend task done.

## Testing
- Tests use a local `stayfit_test` Postgres DB, never Neon (`tests/conftest.py` pins the URLs).
- Never call real external APIs (Google, JEV) in tests. Stub them, or use an `httpx2.MockTransport`.

## Git
- Never commit directly to `main`. Branch, push, and open a PR.
- PRs are squash-merged. After a merge, start new work from a fresh `origin/main`, not the old branch.
- Never stash on one branch and pop on another.
