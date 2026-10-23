from collections.abc import AsyncIterator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

# Sync engine; the app is async, tests use this to set up and inspect data.
engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

# Async engine for the app; psycopg 3 serves both from the same URL.
async_engine = create_async_engine(settings.database_url, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(bind=async_engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_async_db() -> AsyncIterator[AsyncSession]:
    # The session checks out a connection lazily, on its first query.
    async with AsyncSessionLocal() as db:
        yield db
