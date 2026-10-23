import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import AuthSession
from app.services import auth_service
from app.services.google_auth import InvalidGoogleToken

GOOGLE_CLAIMS = {"email": "Jane@Example.com", "email_verified": True, "name": "Jane Doe"}
WEB = {"X-Client": "web"}
INACTIVITY = timedelta(days=settings.refresh_token_inactivity_days)


@pytest.fixture
def client() -> TestClient:
    # A fresh cookie jar per test; https so the client keeps and sends the Secure cookies.
    return TestClient(app, base_url="https://testserver")


@pytest.fixture(autouse=True)
def fake_google(monkeypatch: pytest.MonkeyPatch) -> None:
    def verify(token: str) -> dict:
        if token != "good-token":
            raise InvalidGoogleToken("bad signature")
        return GOOGLE_CLAIMS

    monkeypatch.setattr(auth_service, "verify_google_id_token", verify)


def login(client: TestClient, timezone: str | None = "Asia/Kolkata", headers=None):
    return client.post(
        "/auth/google", json={"id_token": "good-token", "timezone": timezone}, headers=headers
    )


def native_tokens(client: TestClient) -> dict:
    return login(client).json()["tokens"]


def bearer(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def refresh(client: TestClient, refresh_token: str):
    return client.post("/auth/refresh", json={"refresh_token": refresh_token})


def sessions() -> list[AuthSession]:
    with SessionLocal() as db:
        return list(db.scalars(select(AuthSession)))


def update_sessions(**values) -> None:
    with SessionLocal() as db:
        db.execute(update(AuthSession).values(**values))
        db.commit()


def assert_expires_in_inactivity_window(session: AuthSession) -> None:
    expected = datetime.now(UTC) + INACTIVITY
    assert abs(session.expires_at - expected) < timedelta(minutes=1)


# Login (native)


def test_first_login_creates_user_and_returns_tokens(client: TestClient) -> None:
    res = login(client)
    assert res.status_code == 200
    body = res.json()
    assert body["is_new_user"] is True
    assert body["tokens"]["access_token"]
    assert body["tokens"]["refresh_token"]
    assert body["tokens"]["token_type"] == "bearer"
    assert body["tokens"]["expires_in"] == settings.access_token_expire_minutes * 60
    assert body["user"]["email"] == "jane@example.com"
    assert body["user"]["name"] == "Jane Doe"
    assert body["user"]["timezone"] == "Asia/Kolkata"
    assert body["user"]["created_at"]
    assert "set-cookie" not in res.headers


def test_login_starts_a_session_that_expires_after_inactivity(client: TestClient) -> None:
    login(client)
    [session] = sessions()
    assert session.revoked_at is None
    assert_expires_in_inactivity_window(session)


def test_second_login_returns_same_user_with_its_own_session(client: TestClient) -> None:
    first = login(client).json()
    second = login(client, timezone="Europe/London").json()
    assert second["is_new_user"] is False
    assert second["user"]["id"] == first["user"]["id"]
    assert second["user"]["timezone"] == "Asia/Kolkata"
    assert len(sessions()) == 2


def test_invalid_timezone_falls_back_to_utc(client: TestClient) -> None:
    assert login(client, timezone="Not/AZone").json()["user"]["timezone"] == "UTC"


def test_invalid_google_token_is_rejected(client: TestClient) -> None:
    res = client.post("/auth/google", json={"id_token": "forged"})
    assert res.status_code == 401
    assert sessions() == []


# Access token (native)


def test_me_with_access_token(client: TestClient) -> None:
    body = login(client).json()
    res = client.get("/auth/me", headers=bearer(body["tokens"]["access_token"]))
    assert res.status_code == 200
    assert res.json()["id"] == body["user"]["id"]


def test_me_without_valid_token(client: TestClient) -> None:
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers=bearer("garbage")).status_code == 401


def test_expired_access_token_is_rejected(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "access_token_expire_minutes", -1)
    tokens = native_tokens(client)
    assert client.get("/auth/me", headers=bearer(tokens["access_token"])).status_code == 401


# Refresh (native)


def test_refresh_returns_new_tokens_and_extends_session(client: TestClient) -> None:
    tokens = native_tokens(client)
    update_sessions(expires_at=datetime.now(UTC) + timedelta(days=1))

    res = refresh(client, tokens["refresh_token"])
    assert res.status_code == 200
    new = res.json()["tokens"]
    assert new["refresh_token"] != tokens["refresh_token"]
    assert client.get("/auth/me", headers=bearer(new["access_token"])).status_code == 200
    [session] = sessions()
    assert_expires_in_inactivity_window(session)


def test_replaced_refresh_token_is_rejected_but_session_survives(client: TestClient) -> None:
    tokens = native_tokens(client)
    new = refresh(client, tokens["refresh_token"]).json()["tokens"]

    # Within the grace window: treated as a race (e.g. two tabs), not theft.
    assert refresh(client, tokens["refresh_token"]).status_code == 401
    assert refresh(client, new["refresh_token"]).status_code == 200


def test_replaced_refresh_token_reused_later_revokes_session(client: TestClient) -> None:
    tokens = native_tokens(client)
    new = refresh(client, tokens["refresh_token"]).json()["tokens"]
    update_sessions(rotated_at=datetime.now(UTC) - timedelta(minutes=5))

    assert refresh(client, tokens["refresh_token"]).status_code == 401
    [session] = sessions()
    assert session.revoked_at is not None
    # The legitimate holder of the newest token is signed out too.
    assert refresh(client, new["refresh_token"]).status_code == 401


def test_session_inactive_too_long_cannot_refresh(client: TestClient) -> None:
    tokens = native_tokens(client)
    update_sessions(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    assert refresh(client, tokens["refresh_token"]).status_code == 401


def test_refresh_rejects_missing_or_bad_tokens(client: TestClient) -> None:
    native_tokens(client)
    assert client.post("/auth/refresh").status_code == 401
    assert refresh(client, "garbage").status_code == 401
    assert refresh(client, f"{uuid.uuid4()}.secret").status_code == 401
    [session] = sessions()
    assert refresh(client, f"{session.id}.wrong-secret").status_code == 401
    assert session.revoked_at is None


# Logout (native)


def test_logout_revokes_session(client: TestClient) -> None:
    tokens = native_tokens(client)
    res = client.post("/auth/logout", json={"refresh_token": tokens["refresh_token"]})
    assert res.status_code == 200
    assert res.json() == {"status": "signed_out"}
    assert sessions()[0].revoked_at is not None
    assert refresh(client, tokens["refresh_token"]).status_code == 401


def test_logout_with_unknown_or_missing_token_is_ok(client: TestClient) -> None:
    native_tokens(client)
    assert client.post("/auth/logout", json={"refresh_token": "garbage"}).status_code == 200
    assert client.post("/auth/logout").status_code == 200
    assert sessions()[0].revoked_at is None


# Web (httpOnly cookies)


def test_web_login_sets_httponly_cookies_and_returns_no_tokens(client: TestClient) -> None:
    res = login(client, headers=WEB)
    assert res.status_code == 200
    assert res.json()["tokens"] is None
    assert res.json()["user"]["email"] == "jane@example.com"

    cookies = {c.split("=", 1)[0]: c.lower() for c in res.headers.get_list("set-cookie")}
    access, refresh_cookie = cookies["stayfit_access"], cookies["stayfit_refresh"]
    for cookie in (access, refresh_cookie):
        assert "httponly" in cookie
        assert "secure" in cookie
    assert "path=/;" in access and "samesite=lax" in access
    assert "path=/auth" in refresh_cookie and "samesite=strict" in refresh_cookie
    assert f"max-age={settings.access_token_expire_minutes * 60}" in access
    assert f"max-age={int(INACTIVITY.total_seconds())}" in refresh_cookie


def test_web_me_uses_access_cookie(client: TestClient) -> None:
    user = login(client, headers=WEB).json()["user"]
    res = client.get("/auth/me", headers=WEB)
    assert res.status_code == 200
    assert res.json()["id"] == user["id"]


def test_cookies_ignored_without_client_header(client: TestClient) -> None:
    # A cross-site request can carry cookies but can't add the custom header.
    login(client, headers=WEB)
    assert client.get("/auth/me").status_code == 401
    assert client.post("/auth/refresh").status_code == 401


def test_web_refresh_replaces_cookies(client: TestClient) -> None:
    login(client, headers=WEB)
    old_refresh = client.cookies.get("stayfit_refresh")

    res = client.post("/auth/refresh", headers=WEB)
    assert res.status_code == 200
    assert res.json()["tokens"] is None
    assert client.cookies.get("stayfit_refresh") != old_refresh
    assert client.get("/auth/me", headers=WEB).status_code == 200


def test_web_refresh_without_cookie_is_rejected(client: TestClient) -> None:
    assert client.post("/auth/refresh", headers=WEB).status_code == 401


def test_web_logout_clears_cookies_and_revokes_session(client: TestClient) -> None:
    login(client, headers=WEB)
    res = client.post("/auth/logout", headers=WEB)
    assert res.status_code == 200
    assert client.cookies.get("stayfit_access") is None
    assert client.cookies.get("stayfit_refresh") is None
    assert sessions()[0].revoked_at is not None


def test_cors_allows_credentials_only_for_configured_origins(client: TestClient) -> None:
    def preflight(origin: str):
        return client.options(
            "/auth/me",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "X-Client",
            },
        )

    allowed = preflight(settings.cors_origins[0])
    assert allowed.headers["access-control-allow-origin"] == settings.cors_origins[0]
    assert allowed.headers["access-control-allow-credentials"] == "true"
    assert "access-control-allow-origin" not in preflight("https://evil.example").headers
