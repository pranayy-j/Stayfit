from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-only-insecure-secret-do-not-use-in-prod"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "StayFit API"
    environment: str = "development"
    cors_origins: list[str] = ["*"]

    database_url: str = "postgresql+psycopg://stayfit:stayfit@localhost:5432/stayfit"

    # OAuth client IDs whose Google ID tokens we accept (web, iOS, Android).
    google_client_ids: list[str] = []

    jwt_secret: str = DEV_JWT_SECRET
    jwt_expire_days: int = 30


settings = Settings()

if settings.environment != "development" and settings.jwt_secret == DEV_JWT_SECRET:
    raise RuntimeError("JWT_SECRET must be set outside development")
