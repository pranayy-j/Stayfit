# Stayfit
An end to end food-fitness tracker with insights.

## Repository layout

| Folder | Stack |
| --- | --- |
| [`frontend/`](frontend/README.md) | React Native (Expo, TypeScript) for iOS & Android |
| [`backend/`](backend/README.md) | Python 3.12, FastAPI, uv |

The two are independent projects with their own dependencies. Both run locally only for now.
The app talks to the API over HTTP using `EXPO_PUBLIC_API_URL`.

## Quick start

```bash
# terminal 1 — API on :8000
cd backend && uv sync && uv run uvicorn app.main:app --reload --host 0.0.0.0

# terminal 2 — mobile app
cd frontend && npm install && npm start
```
