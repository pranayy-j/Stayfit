from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-only-insecure-secret-do-not-use-in-prod"

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # Later files win: `neon deploy` / `neon env pull` writes the repo-root .env.local,
    # and backend/.env can override it. Real environment variables beat both.
    model_config = SettingsConfigDict(env_file=(REPO_ROOT / ".env.local", ".env"), extra="ignore")

    app_name: str = "StayFit API"
    environment: str = "development"
    cors_origins: list[str] = ["*"]

    # Neon pooled connection (-pooler host) for app traffic.
    database_url: str = "postgresql+psycopg://stayfit:stayfit@localhost:5432/stayfit"
    # Neon direct connection for migrations (Alembic). Falls back to database_url.
    database_url_unpooled: str | None = None

    # OAuth client IDs whose Google ID tokens we accept (web, iOS, Android).
    google_client_ids: list[str] = []

    jwt_secret: str = DEV_JWT_SECRET
    jwt_expire_days: int = 30

    @field_validator("database_url", "database_url_unpooled")
    @classmethod
    def _use_psycopg_driver(cls, url: str | None) -> str | None:
        # Neon hands out plain postgresql:// URLs; SQLAlchemy would pick psycopg2 for those.
        if url and url.startswith(("postgresql://", "postgres://")):
            return "postgresql+psycopg://" + url.split("://", 1)[1]
        return url

    @property
    def migrations_database_url(self) -> str:
        return self.database_url_unpooled or self.database_url


settings = Settings()

if settings.environment != "development" and settings.jwt_secret == DEV_JWT_SECRET:
    raise RuntimeError("JWT_SECRET must be set outside development")
