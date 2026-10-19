from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Shape of every HTTPException body (401, 502, ...)."""

    detail: str = Field(examples=["Not authenticated"])


class HealthResponse(BaseModel):
    status: str = Field(examples=["ok"])


# Reusable `responses=` entries so error shapes appear in the OpenAPI schema for the FE.
UNAUTHORIZED = {401: {"model": ErrorResponse, "description": "Missing or invalid bearer token"}}
