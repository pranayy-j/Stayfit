# StayFit Backend

FastAPI service. Managed with [uv](https://docs.astral.sh/uv/), Python 3.12.

## Develop

```bash
cp .env.example .env
uv sync
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- API docs: http://localhost:8000/docs
- Health check: http://localhost:8000/health

## Test & lint

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
