import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typesafe_sdk import TypeSafeError

from app.controllers.deps import get_current_user
from app.db import get_db
from app.models import User
from app.schemas.common import UNAUTHORIZED, ErrorResponse
from app.schemas.voice_update import VoiceUpdateRequest, VoiceUpdateResponse
from app.services.voice_update_service import VoiceUpdateService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["voice"])


def get_voice_update_service(db: Annotated[Session, Depends(get_db)]) -> VoiceUpdateService:
    return VoiceUpdateService(db)


@router.post(
    "/voice-update",
    responses={
        **UNAUTHORIZED,
        502: {"model": ErrorResponse, "description": "Transcript classification failed"},
    },
)
async def voice_update(
    body: VoiceUpdateRequest,
    user: Annotated[User, Depends(get_current_user)],
    service: Annotated[VoiceUpdateService, Depends(get_voice_update_service)],
) -> VoiceUpdateResponse:
    try:
        is_eating_update = await service.process(user, body.voice_transcript, body.timestamp)
    except TypeSafeError as e:
        logger.exception("JEV classification failed for user %s", user.id)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Transcript classification failed") from e
    return VoiceUpdateResponse(is_eating_update=is_eating_update)
