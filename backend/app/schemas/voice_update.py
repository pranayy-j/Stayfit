from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# ~1000 words of speech is roughly 6-7k characters; leave headroom.
MAX_TRANSCRIPT_CHARS = 10_000


class VoiceUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    voice_transcript: str = Field(
        alias="voice-transcript", min_length=1, max_length=MAX_TRANSCRIPT_CHARS
    )
    timestamp: datetime


class VoiceUpdateResponse(BaseModel):
    status: str = "received"
