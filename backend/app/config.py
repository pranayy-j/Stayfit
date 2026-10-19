from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "StayFit API"
    environment: str = "development"
    cors_origins: list[str] = ["*"]


settings = Settings()
