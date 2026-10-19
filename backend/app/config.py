from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # Later files win: `neon deploy` / `neon env pull` writes the repo-root .env.local,
    # and backend/.env can override it. Real environment variables beat both.
    model_config = SettingsConfigDict(env_file=(REPO_ROOT / ".env.local", ".env"), extra="ignore")

    # Neon pooled connection (-pooler host) for app traffic.
    database_url: str = "postgresql+psycopg://stayfit:stayfit@localhost:5432/stayfit"
    # Neon direct connection for migrations (Alembic). Falls back to database_url.
    database_url_unpooled: str | None = None

    # OAuth client IDs whose Google ID tokens we accept (web, iOS, Android).
    google_client_ids: list[str] = []

    jwt_secret: str = "dev-only-insecure-secret"
    jwt_expire_days: int = 30

    # TypeSafe AI key for JEV (transcript classification).
    typesafe_api_key: str | None = None

    # Anthropic key for Claude (food extraction).
    anthropic_api_key: str | None = None

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
