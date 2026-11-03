import os
from pathlib import Path

# Must be set before app.config is imported. Both URLs are pinned so tests (which truncate
# tables) never touch the Neon database configured in .env.local.
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://stayfit:stayfit@localhost:5432/stayfit_test"
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["DATABASE_URL_UNPOOLED"] = TEST_DATABASE_URL
# Auth settings the tests rely on, independent of any local .env.
os.environ["CORS_ORIGINS"] = '["http://localhost:8081"]'
os.environ["COOKIE_SECURE"] = "true"

import pytest  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from alembic import command  # noqa: E402
from app.db import engine  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _create_database_if_missing() -> None:
    url = make_url(os.environ["DATABASE_URL"])
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": url.database}
        )
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()


@pytest.fixture(scope="session", autouse=True)
def _migrated_db() -> None:
    _create_database_if_missing()
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")


@pytest.fixture(autouse=True)
def _clean_tables() -> None:
    yield
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE users, voice_updates, auth_sessions, eating_tracker, food_aliases, "
                "calorie_chart"
            )
        )
