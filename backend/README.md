# StayFit Backend

FastAPI service. Managed with [uv](https://docs.astral.sh/uv/), Python 3.12.

## Develop

```bash
# from the repo root, once: links the Neon project and writes DATABASE_URL(_UNPOOLED) to .env.local
neon deploy                   # or: neon env pull
cp .env.example .env          # optional overrides (GOOGLE_CLIENT_IDS, JWT_SECRET…)
uv sync
uv run alembic upgrade head   # apply DB migrations (uses the direct, unpooled Neon URL)
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- API docs: http://localhost:8000/docs
- Health check: http://localhost:8000/health

## Layout

Requests flow `controllers → services → repositories`; each layer only calls the one below it.

- `app/controllers/` — FastAPI routers and dependencies. HTTP only: parse requests, call a
  service, map results and domain errors to responses/status codes.
- `app/services/` — business logic and external integrations (Google, JWT). Owns transactions
  (`commit`/`rollback`); knows nothing about HTTP.
- `app/workflows/` — LangGraph pipelines for multi-step AI flows (e.g. voice update: classify →
  store). Nodes call services/repositories; the calling service owns the transaction.
- `app/repositories/` — database access (queries, `add`/`flush`). No business rules, no commits.
- `app/models/` — SQLAlchemy ORM tables. `app/schemas/` — Pydantic request/response models.

## Auth

The app signs in with Google natively, then sends the Google ID token to `POST /auth/google`.
The API verifies it against `GOOGLE_CLIENT_IDS`, creates the user on first login, and returns its
own bearer token (JWT signed with `JWT_SECRET`). `GET /auth/me` returns the current user.

## Migrations

```bash
uv run alembic revision --autogenerate -m "describe change"   # after editing app/models
uv run alembic upgrade head
```

## Test & lint

Tests run against a local Postgres (`docker compose up -d`), never Neon: `tests/conftest.py`
pins both database URLs to a `stayfit_test` database (override with `TEST_DATABASE_URL`).

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

