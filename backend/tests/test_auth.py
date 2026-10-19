import pytest
from fastapi.testclient import TestClient

from app.api.routes import auth as auth_routes
from app.auth.google import InvalidGoogleToken
from app.main import app

client = TestClient(app)

GOOGLE_CLAIMS = {"email": "Jane@Example.com", "email_verified": True, "name": "Jane Doe"}


@pytest.fixture
def fake_google(monkeypatch: pytest.MonkeyPatch) -> None:
    def verify(token: str) -> dict:
        if token != "good-token":
            raise InvalidGoogleToken("bad signature")
        return GOOGLE_CLAIMS

    monkeypatch.setattr(auth_routes, "verify_google_id_token", verify)


def login(timezone: str | None = "Asia/Kolkata"):
    return client.post("/auth/google", json={"id_token": "good-token", "timezone": timezone})


def test_first_login_creates_user(fake_google: None) -> None:
    res = login()
    assert res.status_code == 200
    body = res.json()
    assert body["is_new_user"] is True
    assert body["access_token"]
    assert body["user"]["email"] == "jane@example.com"
    assert body["user"]["name"] == "Jane Doe"
    assert body["user"]["timezone"] == "Asia/Kolkata"
    assert body["user"]["created_at"]


def test_second_login_returns_same_user(fake_google: None) -> None:
    first = login().json()
    second = login(timezone="Europe/London").json()
    assert second["is_new_user"] is False
    assert second["user"]["id"] == first["user"]["id"]
    assert second["user"]["timezone"] == "Asia/Kolkata"


def test_invalid_timezone_falls_back_to_utc(fake_google: None) -> None:
    assert login(timezone="Not/AZone").json()["user"]["timezone"] == "UTC"


def test_invalid_google_token_is_rejected(fake_google: None) -> None:
    res = client.post("/auth/google", json={"id_token": "forged"})
    assert res.status_code == 401


def test_me_with_token(fake_google: None) -> None:
    body = login().json()
    res = client.get("/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert res.status_code == 200
    assert res.json()["id"] == body["user"]["id"]


def test_me_without_token() -> None:
    assert client.get("/auth/me").status_code == 401
    bad = client.get("/auth/me", headers={"Authorization": "Bearer garbage"})
    assert bad.status_code == 401
