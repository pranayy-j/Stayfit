# StayFit

A food and fitness tracker you talk to. Say what you ate in plain speech, in any cuisine and in
English, Hindi or Hinglish ("had two rotis and dal for lunch"). StayFit works out the foods,
quantities and meal time, and logs calories and macros for you.

## What works today

- **Google sign-in** on iOS, Android and web. Sessions use short-lived access tokens and refresh
  tokens, so users stay signed in until they've been inactive for 30 days.
- **Voice food logging.** `POST /v1/voice-update` takes a transcript and a timestamp:
  1. JEV (TypeSafe AI) decides whether the transcript is about eating.
  2. Claude pulls out each food, how much was eaten and when. If anything is unclear, the API
     returns `422 needs_detail` saying what's missing (what / when / how much) and stores nothing.
  3. Otherwise the API responds right away. Calories, protein, carbs, fats and fibre are then
     logged in the background.
- **A calorie chart that grows by itself.** A food we haven't seen yet gets its nutrition per
  100 g / 100 ml estimated by Claude and is added to the chart. A different name for a food we
  already have ("kela" for banana) is matched by meaning (Voyage AI embeddings + pgvector, then
  Claude confirms). The match is saved as an alias, so next time it's an exact lookup.
- **Recording and voice logging in the app.** Record what you ate in the app and it's sent to
  the API to be logged.
- **Daily food log** in the app, with calorie and macro totals for the day.

## Planned

- Fitness tracking
- Insights across food and fitness

## Repository layout

| Folder | Stack |
| --- | --- |
| [`frontend/`](frontend/README.md) | Expo / React Native (TypeScript) for iOS, Android and web |
| [`backend/`](backend/README.md) | Python 3.12, FastAPI, SQLAlchemy 2, Alembic, LangGraph, uv. Postgres (pgvector) on Neon |

The two are independent projects with their own dependencies. The app calls the API over HTTP at
`EXPO_PUBLIC_API_URL`. Both run locally for now. Neither is deployed yet.

```
App ──Google ID token──▶ POST /auth/google ──▶ access + refresh tokens
App ──transcript───────▶ POST /v1/voice-update
                           └─ LangGraph: classify (JEV) → extract (Claude) → save → respond
                                          └─ background: look up / match / estimate foods → eating log
```

## Quick start

You need [uv](https://docs.astral.sh/uv/), Node 22, the [Neon CLI](https://neon.com/docs), and
Docker (only for running backend tests). The backend needs API keys for TypeSafe AI, Anthropic and
Voyage AI, plus Google OAuth client IDs. See [`backend/.env.example`](backend/.env.example) and
[`frontend/.env.example`](frontend/.env.example).

```bash
# once, from the repo root: link the Neon project and write DATABASE_URL to .env.local
neon env pull

# terminal 1: API on :8000
cd backend && uv sync && uv run alembic upgrade head
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# terminal 2: the app (a dev build, since Google Sign-In doesn't run in Expo Go)
cd frontend && npm install && npx expo run:ios    # or: run:android, npm run web
```

The sub-READMEs cover each project's full setup, architecture, tests and checks.

## Contributing

- Never commit to `main`. Branch, push and open a PR. PRs are squash-merged.
- CI runs ruff and pytest for the backend and typecheck and `expo-doctor` for the frontend.
- Architecture and coding rules: [`CLAUDE.md`](CLAUDE.md) and
  [`frontend/AGENTS.md`](frontend/AGENTS.md).
