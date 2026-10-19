# StayFit Backend

FastAPI service. Managed with [uv](https://docs.astral.sh/uv/), Python 3.12.

## Develop

```bash
cp .env.example .env
docker compose up -d          # local Postgres on :5432
uv sync
uv run alembic upgrade head   # apply DB migrations
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

Tests need Postgres running (`docker compose up -d`); they use a separate `stayfit_test` database.

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
