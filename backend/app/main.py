from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.controllers import auth, health

app = FastAPI(title="StayFit API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
