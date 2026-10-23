import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.controllers.deps import get_current_user
from app.db import get_async_db
from app.models import User
from app.schemas.common import UNAUTHORIZED, ErrorResponse
from app.schemas.voice_update import (
    MAX_TRANSCRIPT_CHARS,
    NeedsDetailResponse,
    VoiceUpdateRequest,
    VoiceUpdateResponse,
)
from app.services.eating_classifier import ClassificationError
from app.services.food_extractor import ExtractionError
from app.services.voice_update_service import (
    NeedsDetailError,
    VoiceUpdateService,
    log_food_items_in_background,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["voice"])


def get_voice_update_service(
    db: Annotated[AsyncSession, Depends(get_async_db)],
) -> VoiceUpdateService:
    return VoiceUpdateService(db)


@router.post(
    "/voice-update",
    response_model=VoiceUpdateResponse,
    responses={
        **UNAUTHORIZED,
        413: {"model": ErrorResponse, "description": "Transcript too long"},
        422: {
            "model": NeedsDetailResponse,
            "description": (
                "Eating update needs more detail (what / when / how much); nothing is stored. "
                "Request validation errors also use 422, with a list as `detail`."
            ),
        },
        502: {"model": ErrorResponse, "description": "JEV or Claude call failed"},
    },
)
async def voice_update(
    body: VoiceUpdateRequest,
    user: Annotated[User, Depends(get_current_user)],
    service: Annotated[VoiceUpdateService, Depends(get_voice_update_service)],
    background_tasks: BackgroundTasks,
) -> VoiceUpdateResponse | JSONResponse:
    if len(body.voice_transcript) > MAX_TRANSCRIPT_CHARS:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Transcript too long")
    try:
        result = await service.process(user, body.voice_transcript, body.timestamp)
    except ClassificationError as e:
        logger.exception("JEV classification failed for user %s", user.id)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Transcript classification failed") from e
    except ExtractionError as e:
        logger.exception("Claude food extraction failed for user %s", user.id)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Food extraction failed") from e
    except NeedsDetailError as e:
        logger.info("Voice update needs detail for user %s: %s", user.id, e.missing)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=NeedsDetailResponse(missing=e.missing, items=e.items).model_dump(),
        )

    if result.eating_status == "accepted":
        # Runs after the response is sent.
        background_tasks.add_task(log_food_items_in_background, result.id)
    return VoiceUpdateResponse(
        id=result.id,
        created_at=result.created_at,
        is_eating_update=result.is_eating_update,
        eating_status=result.eating_status,
    )
