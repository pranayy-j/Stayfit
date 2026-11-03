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

## Endpoints

| Route | What it does |
| --- | --- |
| `GET /health` | Health check |
| `POST /auth/google` | Exchange a Google ID token for our tokens; creates the user on first login |
| `POST /auth/refresh` | Get a new access token (and a new refresh token) |
| `POST /auth/logout` | Revoke the session |
| `GET /auth/me` | The signed-in user |
| `POST /v1/voice-update` | Classify a transcript and, for an eating update, log its foods |

## Auth

The app signs in with Google, then sends the Google ID token to `POST /auth/google`. The API
verifies it against `GOOGLE_CLIENT_IDS`, creates the user on first login, and returns two tokens:

- An **access token**: a JWT signed with `JWT_SECRET`, valid for `ACCESS_TOKEN_EXPIRE_MINUTES` (15).
- A **refresh token**, stored hashed in `auth_sessions`. Each `POST /auth/refresh` swaps it for a
  new one. A session ends after `REFRESH_TOKEN_INACTIVITY_DAYS` (30) without a refresh.

Native apps get the tokens in the response body and send `Authorization: Bearer <access token>`.
The web app sends `X-Client: web` on every request; for those requests the tokens are set as
httpOnly cookies instead and never appear in the body. Cookies are honoured only with that header,
which also guards against cross-site request forgery. Web origins must be listed in
`CORS_ORIGINS`.

## Voice updates

`POST /v1/voice-update` runs the LangGraph pipeline in `app/workflows/voice_update_graph.py`:

1. **Classify** (JEV via `langchain-typesafe`): is this about eating? If not, the update is stored
   and that's it.
2. **Extract** (Claude): each food's name, quantity and time. If any item's what / when / how much
   is unclear, the API returns `422` with `detail: "needs_detail"` and the missing parts, and
   stores nothing.
3. **Save and respond.** The voice update is committed with `food_logging_status = pending`, and
   the API responds `200` with `eating_status: "accepted"`.
4. **Log in the background.** The paused run resumes: look the foods up in `calorie_chart`, match
   new names to chart foods by meaning (below), have Claude estimate nutrition for the rest, then
   write one `eating_tracker` row per food. `food_logging_status` ends as `done` or `failed`.

The paused run is held in memory, so a restart between steps 3 and 4 leaves that update `pending`.

## Migrations

```bash
uv run alembic revision --autogenerate -m "describe change"   # after editing app/models
uv run alembic upgrade head
```

## Finding foods already in the calorie chart

A food name not in `calorie_chart` (say "kela") may be a food that is (banana). Chart foods are
embedded with Voyage AI (`VOYAGE_API_KEY`) into the pgvector column `calorie_chart.embedding`;
a new name's nearest foods go to Claude, which says whether one is the same food. A match is
saved in `food_aliases`, so the next "kela" is an exact lookup. See
`app/workflows/voice_update_graph.py`.

Foods added before this have no embedding and are found by exact name only. Embed them once,
after migrating:

```bash
uv run python -m scripts.backfill_food_embeddings
```

## Test & lint

Tests run against a local Postgres (`docker compose up -d`), never Neon: `tests/conftest.py`
pins both database URLs to a `stayfit_test` database (override with `TEST_DATABASE_URL`).

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

