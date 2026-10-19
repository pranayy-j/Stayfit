import uuid

import pytest
from fastapi.testclient import TestClient
from typesafe_sdk import TypeSafeError

from app.db import SessionLocal
from app.main import app
from app.models import User
from app.schemas.voice_update import MAX_TRANSCRIPT_CHARS
from app.services import eating_classifier
from app.services.token_service import create_access_token

client = TestClient(app)

PAYLOAD = {"voice-transcript": "Ran 5k this morning.", "timestamp": "2026-10-20T07:30:00+05:30"}


@pytest.fixture
def jev_probability(monkeypatch: pytest.MonkeyPatch) -> dict[str, float]:
    """Stub JEV; set holder["p"] to control the returned probability."""
    holder = {"p": 0.9}

    async def fake(_: str) -> float:
        return holder["p"]

    monkeypatch.setattr(eating_classifier, "eating_update_probability", fake)
    return holder


def auth_header() -> dict[str, str]:
    with SessionLocal() as db:
        user = User(id=uuid.uuid4(), name="Jane", email="jane@example.com")
        db.add(user)
        db.commit()
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def test_voice_update_above_threshold_is_eating_update(jev_probability: dict) -> None:
    res = client.post("/v1/voice-update", json=PAYLOAD, headers=auth_header())
    assert res.status_code == 200
    assert res.json() == {"status": "received", "is_eating_update": True}


@pytest.mark.parametrize("p", [0.75, 0.2])
def test_voice_update_at_or_below_threshold_is_not(jev_probability: dict, p: float) -> None:
    jev_probability["p"] = p
    res = client.post("/v1/voice-update", json=PAYLOAD, headers=auth_header())
    assert res.json()["is_eating_update"] is False


def test_voice_update_jev_failure_returns_502(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fail(_: str) -> float:
        raise TypeSafeError("boom")

    monkeypatch.setattr(eating_classifier, "eating_update_probability", fail)
    res = client.post("/v1/voice-update", json=PAYLOAD, headers=auth_header())
    assert res.status_code == 502


def test_voice_update_requires_auth() -> None:
    assert client.post("/v1/voice-update", json=PAYLOAD).status_code == 401


def test_voice_update_validates_body() -> None:
    headers = auth_header()
    missing_ts = {"voice-transcript": "hi"}
    naive_ts = {**PAYLOAD, "timestamp": "2026-10-20T07:30:00"}
    empty = {**PAYLOAD, "voice-transcript": ""}
    for body in (missing_ts, naive_ts, empty):
        assert client.post("/v1/voice-update", json=body, headers=headers).status_code == 422


def test_voice_update_too_long_transcript(jev_probability: dict) -> None:
    headers = auth_header()
    at_limit = {**PAYLOAD, "voice-transcript": "x" * MAX_TRANSCRIPT_CHARS}
    over = {**PAYLOAD, "voice-transcript": "x" * (MAX_TRANSCRIPT_CHARS + 1)}
    assert client.post("/v1/voice-update", json=at_limit, headers=headers).status_code == 200
    res = client.post("/v1/voice-update", json=over, headers=headers)
    assert res.status_code == 413
    assert res.json() == {"detail": "Transcript too long"}
