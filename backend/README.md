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

## Auth

The app signs in with Google natively, then sends the Google ID token to `POST /auth/google`.
The API verifies it against `GOOGLE_CLIENT_IDS`, creates the user on first login, and returns its
own bearer token (JWT signed with `JWT_SECRET`). `GET /auth/me` returns the current user.

## Migrations

```bash
uv run alembic revision --autogenerate -m "describe change"   # after editing app/models
uv run alembic upgrade head
```

The Docker image runs `alembic upgrade head` on start.

## Test & lint

Tests run against a local Postgres (`docker compose up -d`), never Neon: `tests/conftest.py`
pins both database URLs to a `stayfit_test` database (override with `TEST_DATABASE_URL`).

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

## Deploy

The `Dockerfile` builds a standalone image that listens on `$PORT` (default 8000), so it runs on
any container host (Render, Railway, Fly.io, Cloud Run, ECS…):

```bash
docker build -t stayfit-backend .
docker run -p 8000:8000 --env-file .env stayfit-backend
```

Settings are read from environment variables (see `app/config.py`).
