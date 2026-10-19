from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.controllers.deps import get_current_user
from app.db import get_db
from app.models import User
from app.schemas.voice_update import VoiceUpdateRequest, VoiceUpdateResponse
from app.services.voice_update_service import VoiceUpdateService

router = APIRouter(prefix="/v1", tags=["voice"])


def get_voice_update_service(db: Annotated[Session, Depends(get_db)]) -> VoiceUpdateService:
    return VoiceUpdateService(db)


@router.post("/voice-update", response_model=VoiceUpdateResponse)
def voice_update(
    body: VoiceUpdateRequest,
    user: Annotated[User, Depends(get_current_user)],
    service: Annotated[VoiceUpdateService, Depends(get_voice_update_service)],
):
    service.process(user, body.voice_transcript, body.timestamp)
    return VoiceUpdateResponse()
