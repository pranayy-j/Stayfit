# Stayfit
An end to end food-fitness tracker with insights.

## Repository layout

| Folder | Stack | Deployed as |
| --- | --- | --- |
| [`frontend/`](frontend/README.md) | React Native (Expo, TypeScript) for iOS & Android | App Store / Play Store via EAS Build |
| [`backend/`](backend/README.md) | Python 3.12, FastAPI, uv | Docker container |

The two are independent projects with their own dependencies, and they're deployed separately.
The app talks to the API over HTTP using `EXPO_PUBLIC_API_URL`.

## Quick start

```bash
# terminal 1 — API on :8000
cd backend && uv sync && uv run uvicorn app.main:app --reload --host 0.0.0.0

# terminal 2 — mobile app
cd frontend && npm install && npm start
```
