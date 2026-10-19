from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.controllers import auth, health, voice_update
from app.db import async_engine
from app.services import eating_classifier, food_extractor


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await eating_classifier.close_client()
    await food_extractor.close_client()
    await async_engine.dispose()


app = FastAPI(title="StayFit API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(voice_update.router)
