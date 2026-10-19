from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from app.config import settings

_request = google_requests.Request()


class InvalidGoogleToken(Exception):
    pass


def verify_google_id_token(token: str) -> dict:
    """Verify a Google ID token's signature, expiry and audience; return its claims."""
    if not settings.google_client_ids:
        raise RuntimeError("GOOGLE_CLIENT_IDS is not configured")
    try:
        claims = id_token.verify_oauth2_token(token, _request, audience=settings.google_client_ids)
    except ValueError as e:
        raise InvalidGoogleToken(str(e)) from e
    if not claims.get("email") or not claims.get("email_verified"):
        raise InvalidGoogleToken("Google account has no verified email")
    return claims
